"""End-to-end simulate: real watchdog + real fake-ZEN process + real CZI files +
the real wizard running as a subprocess in --auto-accept mode.

This is the M0/M1 exit criterion: the full lifecycle works on a dev machine with
no microscope attached.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from after_scope.appcontext import AppContext
from after_scope.db import repo
from after_scope.watchdog.service import State, WatchdogService

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_config(tmp_path: Path) -> Path:
    cfg = textwrap.dedent(f"""
        instrument: {{ name: "E2E scope", machine: "e2e" }}
        zen:
          process_names: []
          cmdline_contains: "AFTER_SCOPE_FAKE_ZEN_E2E"
          poll_seconds: 0.2
        watch_dirs:
          - {{ path: "{(tmp_path / 'scratch').as_posix()}" }}
        scan: {{ seconds: 1 }}
        dropbox: {{ root: "{(tmp_path / 'dropbox').as_posix()}" }}
        roster:
          - {{ name: "Tim de Wet", initials: "TdW" }}
          - {{ name: "Jane Doe", initials: "JD" }}
        ui: {{ kiosk: false }}
        tray: {{ enabled: false }}
        data_dir: "{(tmp_path / 'data').as_posix()}"
    """)
    p = tmp_path / "config.yaml"
    p.write_text(cfg, encoding="utf-8")
    (tmp_path / "scratch").mkdir()
    return p


def _spawn_wizard_auto(ctx, reason, session_id):
    env = dict(os.environ)
    env.update({"QT_QPA_PLATFORM": "offscreen", "AFTER_SCOPE_AUTO_USER": "TdW"})
    cmd = [
        sys.executable, "-m", "after_scope", "--config", str(ctx.config_path),
        "wizard", "--session-id", str(session_id), "--reason", reason, "--auto-accept",
    ]
    result = subprocess.run(
        cmd, env=env, cwd=REPO_ROOT, capture_output=True, text=True, timeout=120
    )
    if result.returncode not in (0, 2, 3, 4):
        print("wizard stderr:", result.stderr[-2000:])
    return result.returncode


def _step_until(svc, predicate, timeout=30.0, tick=0.2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        svc.step()
        if predicate():
            return True
        time.sleep(tick)
    return False


def test_full_simulated_session(tmp_path):
    config_path = _write_config(tmp_path)
    ctx = AppContext.build(str(config_path), role="e2e", with_logging=False)
    toast_calls: list[tuple[int, list[int]]] = []
    svc = WatchdogService(
        ctx, spawn_wizard=_spawn_wizard_auto,
        spawn_toast=lambda _ctx, sid, ids: toast_calls.append((sid, list(ids))),
    )

    fake_zen = subprocess.Popen(
        [sys.executable, "-c",
         "import time\nimport sys\n# AFTER_SCOPE_FAKE_ZEN_E2E marker\nwhile True: time.sleep(0.2)",
         "AFTER_SCOPE_FAKE_ZEN_E2E"],
    )
    try:
        # 1. watchdog notices ZEN and runs the pre-use check
        assert _step_until(svc, lambda: svc.state == State.ACTIVE, timeout=15)
        sid = svc.session_id
        assert sid is not None
        row = repo.get_session(ctx.db, sid)
        assert row["user_id"] is not None       # pre-use wizard identified TdW
        assert row["arrival_state_ok"] == 1

        # 1b. the pre-use declaration created the scratch session folder
        assert row["planned_strain"] == "TEST1"
        planned_dir = Path(row["planned_dir"])
        assert planned_dir.is_dir() and "e2e-experiment" in planned_dir.name
        assert planned_dir in svc.scanner.extra_dirs or any(
            planned_dir.is_relative_to(root) for root, _ in svc.scanner.watch_dirs
        )

        # 2. "acquire" files: one INTO the planned session folder (proves session-
        #    scoped watching), one in scratch root, one dust reference
        from scripts.make_fixture_czi import make_fixture_czi

        scratch = tmp_path / "scratch"
        make_fixture_czi(planned_dir / "Snap-001.czi")
        make_fixture_czi(scratch / "Snap-002.czi")
        make_fixture_czi(scratch / "dustref_check.czi", channels=1)

        assert _step_until(
            svc, lambda: len(repo.session_files(ctx.db, sid)) >= 3, timeout=30
        ), "scanner never ingested the files"
        files = repo.session_files(ctx.db, sid)
        assert any(f["status"] == "dust_ref" for f in files)
        assert all(f["dims_json"] for f in files)  # real CZI metadata extracted

        # 2b. declared plan auto-applied at ingest, BEFORE any end-of-session wizard
        tagged = [f for f in files if f["status"] != "dust_ref"]
        assert all(f["strain"] == "TEST1" and f["condition"] == "ctrl" for f in tagged)
        assert all(f["experiment_id"] is not None for f in tagged)
        # toast fired for the data files only
        assert toast_calls and all(call[0] == sid for call in toast_calls)
        toasted = {fid for _, ids in toast_calls for fid in ids}
        assert toasted == {f["id"] for f in tagged}

        # 3. close ZEN -> debounce -> end-of-session wizard (auto) -> complete
        fake_zen.terminate()
        fake_zen.wait(timeout=10)
        assert _step_until(svc, lambda: svc.state == State.IDLE, timeout=45)

        row = repo.get_session(ctx.db, sid)
        assert row["status"] == "complete"
        assert row["ended_reason"] in ("zen_close", "crash")  # SIGTERM exit code is platform-dependent
        assert row["checklist_completed_at"]

        # 4. files filed into the standardized tree with template names
        moved = [f for f in repo.session_files(ctx.db, sid) if f["status"] == "moved"]
        assert len(moved) == 2
        for f in moved:
            path = Path(f["current_path"])
            assert path.exists()
            assert "MicroscopeData" in str(path) and "TdW" in str(path)
            assert "e2e-experiment" in path.name and "TEST1" in path.name

        # 5. dust ref registered and filed under dustrefs/
        ref = repo.session_dust_ref(ctx.db, sid)
        assert ref is not None and ref["method"] == "manual"
        dust_file = repo.get_file(ctx.db, ref["file_id"])
        assert "dustrefs" in dust_file["current_path"]
        assert Path(dust_file["current_path"]).exists()

        # 6. Dropbox artifacts regenerated
        exports = ctx.config.exports_dir
        assert (exports / "sessions.csv").exists()
        assert (exports / "files_catalog.csv").exists()
        dashboard = ctx.config.dashboard_dir / "index.html"
        assert dashboard.exists()
        content = dashboard.read_text(encoding="utf-8")
        assert "Tim de Wet" in content

        # 7. checklist rows persisted by the subprocess wizard
        keys = {r["item_key"] for r in repo.checklist_responses(ctx.db, sid)}
        assert {"stage_clean", "dust_cover", "sample_removed"} <= keys
    finally:
        if fake_zen.poll() is None:
            fake_zen.kill()
