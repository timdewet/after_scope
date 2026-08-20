"""Plan and execute standardized renames/moves (copy → verify → delete, audited).

Every filed image gets a human-readable YAML sidecar (<name>.czi.yaml) next to
it: biological details as declared, imaging details as read from the CZI header,
user and session context — so the file remains self-describing outside the
catalog (best-effort; a sidecar failure never fails the move).
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..config import AppConfig
from ..db import repo
from .naming import build_context, propose_filename, render_dest_dir

log = logging.getLogger(__name__)


@dataclass
class MovePlan:
    file_id: int
    src: Path
    dst: Path
    action: str  # move | copy | index_only


def _file_context(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    initials = None
    if row["user_id"]:
        user = repo.get_user(conn, row["user_id"])
        initials = user["initials"] if user else None
    experiment = None
    if row["experiment_id"]:
        exp = conn.execute(
            "SELECT name FROM experiments WHERE id=?", (row["experiment_id"],)
        ).fetchone()
        experiment = exp["name"] if exp else None
    return build_context(
        acquired_at=row["acquired_at"],
        initials=initials,
        experiment=experiment,
        strain=row["strain"],
        condition=row["condition"],
        original_stem=Path(row["current_path"]).stem,
    )


def plan_moves(conn: sqlite3.Connection, session_id: int, cfg: AppConfig) -> list[MovePlan]:
    """Propose a destination for every organizable file in the session."""
    plans: list[MovePlan] = []
    taken: dict[Path, set[str]] = {}
    mode = cfg.organize.mode
    for row in repo.session_files(conn, session_id):
        src = Path(row["current_path"])
        if row["status"] in ("excluded", "moved", "copied", "missing"):
            continue
        ctx = _file_context(conn, row)
        if row["status"] == "dust_ref":
            dest_dir = cfg.afterscope_root / "dustrefs" / ctx["year"]
            name = f"dustref_{ctx['date']}_{ctx['time']}{src.suffix}"
            i, base = 2, name
            while name in taken.get(dest_dir, set()) or (dest_dir / name).exists():
                name = f"{Path(base).stem}-{i}{src.suffix}"
                i += 1
        else:
            if mode == "index_only":
                plans.append(MovePlan(row["id"], src, src, "index_only"))
                continue
            dest_dir = render_dest_dir(cfg.organize.dest_template, ctx, cfg.dropbox.root)
            name = propose_filename(
                cfg.organize.filename_template,
                ctx,
                dest_dir,
                src.suffix,
                taken.setdefault(dest_dir, set()),
                cfg.organize.max_path_length,
            )
        taken.setdefault(dest_dir, set()).add(name)
        action = "move" if mode == "move" or row["status"] == "dust_ref" else mode
        plans.append(MovePlan(row["id"], src, dest_dir / name, action))
    return plans


def execute_plans(conn: sqlite3.Connection, plans: list[MovePlan]) -> dict[int, str]:
    """Run each plan; returns {file_id: outcome}. Failures never abort the batch."""
    results: dict[int, str] = {}
    for plan in plans:
        try:
            results[plan.file_id] = _execute_one(conn, plan)
        except Exception:
            log.error("Organize failed for file %s", plan.src, exc_info=True)
            repo.set_file_status(conn, plan.file_id, "move_failed")
            results[plan.file_id] = "move_failed"
    return results


def _execute_one(conn: sqlite3.Connection, plan: MovePlan) -> str:
    if plan.action == "index_only" or plan.src == plan.dst:
        repo.set_file_status(conn, plan.file_id, "indexed")
        return "indexed"
    if not plan.src.exists():
        repo.set_file_status(conn, plan.file_id, "missing")
        return "missing"
    plan.dst.parent.mkdir(parents=True, exist_ok=True)
    if plan.dst.exists():  # never overwrite — planner should have avoided this
        repo.set_file_status(conn, plan.file_id, "move_failed")
        return "move_failed"
    shutil.copy2(plan.src, plan.dst)
    if plan.dst.stat().st_size != plan.src.stat().st_size:
        plan.dst.unlink(missing_ok=True)
        repo.set_file_status(conn, plan.file_id, "move_failed")
        return "move_failed"
    row = repo.get_file(conn, plan.file_id)
    was_dust = row["status"] == "dust_ref"
    if plan.action == "move":
        plan.src.unlink()
        repo.record_move(conn, plan.file_id, str(plan.src), str(plan.dst), verified=True)
        if not was_dust:
            repo.set_file_status(conn, plan.file_id, "moved")
            _write_sidecar_safely(conn, plan.file_id, plan.dst)
        return "moved"
    repo.record_move(conn, plan.file_id, str(plan.src), str(plan.dst), verified=True)
    if not was_dust:
        repo.set_file_status(conn, plan.file_id, "copied")
        _write_sidecar_safely(conn, plan.file_id, plan.dst)
    return "copied"


def _prune(value):
    if isinstance(value, dict):
        cleaned = {k: _prune(v) for k, v in value.items()}
        return {k: v for k, v in cleaned.items() if v not in (None, {}, [])}
    return value


def write_sidecar(conn: sqlite3.Connection, file_id: int, dst: Path) -> Path | None:
    """Write <dst>.yaml describing the filed image; returns the sidecar path."""
    row = repo.get_file(conn, file_id)
    if row is None:
        return None
    session = repo.get_session(conn, row["session_id"]) if row["session_id"] else None
    user = repo.get_user(conn, row["user_id"]) if row["user_id"] else None
    experiment = None
    if row["experiment_id"]:
        r = conn.execute(
            "SELECT name FROM experiments WHERE id=?", (row["experiment_id"],)
        ).fetchone()
        experiment = r["name"] if r else None
    channels = None
    if row["channels_json"]:
        channels = [c.get("name") for c in json.loads(row["channels_json"])]
    dims = json.loads(row["dims_json"]) if row["dims_json"] else None
    doc = _prune({
        "file": dst.name,
        "original_name": Path(row["original_path"]).name,
        "acquired_at": row["acquired_at"],
        "user": f"{user['full_name']} ({user['initials']})" if user else None,
        "biological": {
            "experiment": experiment,
            "strain": row["strain"],
            "condition": row["condition"],
            "preparation": row["coverslip"],
            "notes": row["notes"],
        },
        "imaging": {
            "objective": row["objective_name"],
            "magnification": row["magnification"],
            "numerical_aperture": row["na"],
            "immersion": row["immersion"],
            "pixel_size_um": row["pixel_size_um"],
            "channels": channels,
            "dimensions": dims,
        },
        "session": {
            "started": session["started_at"],
            "machine": session["machine"],
            "planned_imaging": session["planned_imaging"],
        } if session else None,
        "catalogued_by": "AfterScope",
    })
    sidecar = dst.with_name(dst.name + ".yaml")
    sidecar.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return sidecar


def _write_sidecar_safely(conn: sqlite3.Connection, file_id: int, dst: Path) -> None:
    try:
        write_sidecar(conn, file_id, dst)
    except Exception:
        log.warning("Sidecar write failed for %s", dst, exc_info=True)


def undo_move(conn: sqlite3.Connection, move_id: int) -> bool:
    """Reverse a recorded move (copy back → verify → delete)."""
    row = conn.execute("SELECT * FROM file_moves WHERE id=?", (move_id,)).fetchone()
    if not row or row["undone_at"]:
        return False
    src, dst = Path(row["to_path"]), Path(row["from_path"])
    if not src.exists() or dst.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if dst.stat().st_size != src.stat().st_size:
        dst.unlink(missing_ok=True)
        return False
    src.unlink()
    from ..util import now_iso

    with conn:
        conn.execute("UPDATE file_moves SET undone_at=? WHERE id=?", (now_iso(), move_id))
        conn.execute(
            "UPDATE files SET current_path=?, status='indexed' WHERE id=?",
            (str(dst), row["file_id"]),
        )
    return True
