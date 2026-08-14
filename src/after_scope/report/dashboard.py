"""Static, fully self-contained lab dashboard rendered into Dropbox.

No CDNs, no JS dependencies: charts are inline SVG generated here, thumbnails are
copied next to the page. The page must render via file:// on every synced machine.
"""

from __future__ import annotations

import html
import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from ..config import AppConfig
from ..db import repo
from ..paths import AppPaths
from ..util import parse_iso

log = logging.getLogger(__name__)


def svg_bars(data: list[tuple[str, float]], width: int = 640, bar_h: int = 22) -> str:
    """Simple horizontal bar chart as an inline SVG string."""
    if not data:
        return ""
    peak = max(v for _, v in data) or 1
    label_w, gap, value_w = 180, 6, 60
    chart_w = width - label_w - value_w
    height = len(data) * (bar_h + gap)
    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
        f'xmlns="http://www.w3.org/2000/svg">'
    ]
    for i, (label, value) in enumerate(data):
        y = i * (bar_h + gap)
        w = max(2, int(chart_w * value / peak))
        lab = html.escape(str(label)[:28])
        shown = f"{value:g}"
        parts.append(
            f'<text x="{label_w - 8}" y="{y + bar_h - 6}" text-anchor="end" '
            f'class="bar-label">{lab}</text>'
            f'<rect x="{label_w}" y="{y}" width="{w}" height="{bar_h}" rx="3" class="bar"/>'
            f'<text x="{label_w + w + 6}" y="{y + bar_h - 6}" class="bar-value">{shown}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _days_since(iso: str | None, now: datetime) -> int | None:
    if not iso:
        return None
    try:
        return max(0, (now - parse_iso(iso)).days)
    except ValueError:
        return None


def _copy_thumb(src: str | None, thumbs_out: Path, copied: dict[str, str]) -> str | None:
    if not src:
        return None
    if src in copied:
        return copied[src]
    p = Path(src)
    if not p.exists():
        return None
    try:
        thumbs_out.mkdir(parents=True, exist_ok=True)
        dest = thumbs_out / p.name
        shutil.copyfile(p, dest)
        rel = f"thumbs/{p.name}"
        copied[src] = rel
        return rel
    except OSError:
        return None


def collect_context(
    conn: sqlite3.Connection, cfg: AppConfig, dashboard_dir: Path, now: datetime
) -> dict:
    copied: dict[str, str] = {}
    thumbs_out = dashboard_dir / "thumbs"

    sessions = repo.list_sessions(conn)
    ended = [s for s in sessions if s["ended_at"]]
    last = sessions[-1] if sessions else None

    # usage per user (last ~90 days)
    cutoff = now.strftime("%Y-%m-%d")
    usage_rows = conn.execute(
        """SELECT COALESCE(u.full_name, 'unidentified') AS name, COUNT(*) AS n
           FROM sessions s LEFT JOIN users u ON u.id = s.user_id
           WHERE s.started_at >= date(?, '-90 days')
           GROUP BY name ORDER BY n DESC""",
        (cutoff,),
    ).fetchall()

    # solvent per objective
    solvent = []
    objectives = conn.execute(
        """SELECT DISTINCT objective_name FROM maintenance_events
           WHERE type='solvent_clean' AND objective_name IS NOT NULL"""
    ).fetchall()
    oil_objs = conn.execute(
        """SELECT DISTINCT objective_name FROM files
           WHERE objective_name IS NOT NULL AND LOWER(COALESCE(immersion,'')) LIKE '%oil%'"""
    ).fetchall()
    names = {r["objective_name"] for r in objectives} | {r["objective_name"] for r in oil_objs}
    for name in sorted(names):
        last_clean = repo.last_solvent_clean(conn, name)
        days = _days_since(last_clean["created_at"], now) if last_clean else None
        count = conn.execute(
            "SELECT COUNT(*) c FROM maintenance_events WHERE type='solvent_clean' AND objective_name=?",
            (name,),
        ).fetchone()["c"]
        solvent.append(
            {
                "objective": name,
                "days_since": days,
                "count": count,
                "overdue": days is None or days > cfg.solvent.suggest_after_days,
            }
        )

    # dust gallery (latest 12, thumbnails copied)
    dust = []
    for r in repo.dust_refs(conn, limit=12):
        if r["method"] == "skipped":
            continue
        dust.append(
            {
                "date": (r["created_at"] or "")[:10],
                "objective": r["objective_name"] or "?",
                "thumb": _copy_thumb(r["thumbnail_path"], thumbs_out, copied),
            }
        )

    incidents = [dict(r) for r in repo.list_incidents(conn, limit=20)]
    open_incidents = [i for i in incidents if i["status"] == "open"]

    complete = sum(1 for s in ended if s["status"] == "complete")
    skipped = sum(1 for s in ended if s["incomplete_reason"] == "skipped")
    other_incomplete = sum(
        1 for s in ended if s["status"] != "complete" and s["incomplete_reason"] != "skipped"
    )
    dust_sessions = conn.execute(
        "SELECT COUNT(DISTINCT session_id) c FROM dust_refs WHERE method != 'skipped'"
    ).fetchone()["c"]

    maintenance = [dict(r) for r in repo.maintenance_events(conn)[:15]]

    return {
        "instrument": cfg.instrument.name,
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "last_session": dict(last) if last else None,
        "sessions_total": len(sessions),
        "compliance": {
            "complete": complete,
            "skipped": skipped,
            "other_incomplete": other_incomplete,
        },
        "usage_svg": svg_bars([(r["name"], r["n"]) for r in usage_rows]),
        "solvent": solvent,
        "solvent_suggest_days": cfg.solvent.suggest_after_days,
        "dust": dust,
        "dust_sessions": dust_sessions,
        "open_incidents": open_incidents,
        "recent_incidents": incidents[:10],
        "maintenance": maintenance,
    }


def render_dashboard(
    conn: sqlite3.Connection,
    cfg: AppConfig,
    paths: AppPaths,
    now: datetime | None = None,
) -> Path | None:
    now = now or datetime.now()
    dashboard_dir = cfg.dashboard_dir
    try:
        dashboard_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log.error("Cannot create dashboard dir %s", dashboard_dir, exc_info=True)
        return None
    env = Environment(
        loader=PackageLoader("after_scope.report", "templates"),
        autoescape=select_autoescape(["html"]),
    )
    ctx = collect_context(conn, cfg, dashboard_dir, now)
    out = env.get_template("dashboard.html.j2").render(**ctx)
    dest = dashboard_dir / "index.html"
    tmp = dest.with_suffix(".html.tmp")
    tmp.write_text(out, encoding="utf-8")
    tmp.replace(dest)
    return dest
