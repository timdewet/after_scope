"""Watchdog-side ingest of migration manifests (runs on the scope PC only)."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from ..appcontext import AppContext
from ..db import repo

log = logging.getLogger(__name__)


def ingest_inbox(ctx: AppContext) -> int:
    """Process every manifest in the Dropbox inbox. Returns files ingested."""
    inbox = ctx.config.migrations_inbox
    if not inbox.exists():
        return 0
    total = 0
    for path in sorted(inbox.glob("*.json")):
        total += _ingest_one(ctx, path)
    return total


def _move_to(path: Path, subdir: str) -> None:
    dest_dir = path.parent.parent / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), dest_dir / path.name)


def _ingest_one(ctx: AppContext, path: Path) -> int:
    from .manifest import load_manifest

    conn = ctx.db
    try:
        manifest = load_manifest(path)
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        log.error("Bad manifest %s: %s", path.name, exc)
        repo.record_manifest(
            conn, path.name, submitted_by=None, submitted_at=None,
            status="failed", error=str(exc),
        )
        _move_to(path, "failed")
        return 0

    ingested = 0
    errors: list[str] = []
    user = next(
        (u for u in repo.list_users(conn, active_only=False)
         if u["initials"] == manifest.submitted_by),
        None,
    )
    for mf in manifest.files:
        target = Path(mf.new_path)
        if not target.exists():
            errors.append(f"missing: {mf.new_path}")
            continue
        exists = conn.execute(
            "SELECT 1 FROM files WHERE current_path=?", (mf.new_path,)
        ).fetchone()
        if exists:
            continue  # idempotent re-ingest
        file_id = repo.add_file(
            conn, None, mf.original_path, origin="migration", status="moved",
            size_bytes=target.stat().st_size, acquired_at=mf.acquired_at,
        )
        with conn:
            conn.execute("UPDATE files SET current_path=? WHERE id=?", (mf.new_path, file_id))
        meta = {k: v for k, v in mf.extracted.items() if k in (
            "objective_name", "magnification", "na", "immersion", "pixel_size_um",
            "channels_json", "dims_json",
        )}
        if meta:
            repo.set_file_metadata(conn, file_id, meta)
        experiment_id = None
        if mf.experiment:
            experiment_id = repo.get_or_create_experiment(
                conn, mf.experiment, user["id"] if user else None
            )
        repo.set_file_user_meta(
            conn, file_id,
            experiment_id=experiment_id,
            user_id=user["id"] if user else None,
            strain=mf.strain, condition=mf.condition,
            coverslip=mf.coverslip, notes=mf.notes,
        )
        ingested += 1

    status = "ingested" if not errors else "failed"
    repo.record_manifest(
        conn, path.name,
        submitted_by=manifest.submitted_by, submitted_at=manifest.submitted_at,
        status=status, file_count=ingested,
        error="; ".join(errors[:5]) if errors else None,
    )
    _move_to(path, "processed" if not errors else "failed")
    log.info("Manifest %s: %d file(s) ingested, %d error(s)", path.name, ingested, len(errors))
    return ingested
