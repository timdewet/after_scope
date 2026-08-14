from __future__ import annotations

from datetime import datetime

from after_scope.db import repo
from after_scope.report.dashboard import render_dashboard, svg_bars

FROZEN_NOW = datetime(2026, 8, 14, 12, 0, 0)


def _seed(conn, cfg, tmp_path):
    uid = repo.add_user(conn, "Tim de Wet", "TdW")
    sid = repo.open_session(conn, zen_pid=1, started_at="2026-08-14T09:00:00")
    repo.set_session_user(conn, sid, uid, "roster")
    fid = repo.add_file(conn, sid, "/d/a.czi")
    repo.set_file_metadata(
        conn, fid, {"objective_name": "Plan-Apo 100x/1.4 Oil", "immersion": "Oil"}
    )
    # thumbnail on disk so the dashboard copies it
    thumb = tmp_path / "thumb100.png"
    thumb.write_bytes(b"\x89PNG\r\n\x1a\nfakepng")
    dust_fid = repo.add_file(conn, sid, "/d/dustref_1.czi")
    repo.set_file_status(conn, dust_fid, "dust_ref")
    repo.set_file_metadata(conn, dust_fid, {"thumbnail_path": str(thumb)})
    repo.add_dust_ref(conn, session_id=sid, file_id=dust_fid,
                      objective_name="Plan-Apo 100x/1.4 Oil", method="manual")
    repo.add_maintenance_event(conn, "solvent_clean",
                               objective_name="Plan-Apo 100x/1.4 Oil",
                               solvent="ethanol", session_id=sid, user_id=uid)
    repo.add_incident(conn, session_id=sid, reported_by=uid, category="problem",
                      description="Stage squeaks near x=20mm")
    repo.end_session(conn, sid, ended_reason="zen_close")
    repo.set_session_status(conn, sid, "complete")
    return sid


def test_svg_bars_scale_and_escape():
    svg = svg_bars([("Jane <script>", 4), ("Tim", 2)])
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "&lt;script&gt;" in svg
    assert svg_bars([]) == ""


def test_render_dashboard_self_contained(conn, cfg, tmp_path):
    _seed(conn, cfg, tmp_path)
    out = render_dashboard(conn, cfg, None, now=FROZEN_NOW)
    assert out is not None and out.name == "index.html"
    html = out.read_text(encoding="utf-8")
    # content from every section
    assert "Tim de Wet" in html
    assert "Plan-Apo 100x/1.4 Oil" in html
    assert "Stage squeaks" in html
    assert "generated 2026-08-14 12:00" in html
    # self-contained: no external fetches (xmlns namespace URIs are fine)
    assert 'src="http' not in html and 'href="http' not in html
    assert "@import" not in html and "<script src" not in html
    # thumbnail copied next to the page and referenced relatively
    assert 'src="thumbs/thumb100.png"' in html
    assert (out.parent / "thumbs" / "thumb100.png").exists()


def test_render_dashboard_empty_db(conn, cfg):
    out = render_dashboard(conn, cfg, None, now=FROZEN_NOW)
    html = out.read_text(encoding="utf-8")
    assert "No sessions recorded yet" in html


def test_solvent_overdue_flagging(conn, cfg, tmp_path):
    _seed(conn, cfg, tmp_path)
    # a clean logged today is not overdue at suggest_after_days=14
    out = render_dashboard(conn, cfg, None, now=FROZEN_NOW)
    html = out.read_text(encoding="utf-8")
    assert '<td class="ok">' in html and "0 day(s) ago" in html
