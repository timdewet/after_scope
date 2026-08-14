from __future__ import annotations

import time
from pathlib import Path

import pytest

from after_scope.appcontext import AppContext
from after_scope.db import repo
from after_scope.db.connection import apply_migrations, connect
from after_scope.watchdog.file_scan import AcquisitionScanner

pytest.importorskip("PySide6")


@pytest.fixture(autouse=True)
def _ensure_qapp(qapp):
    yield


@pytest.fixture
def ctx(cfg, tmp_path):
    return AppContext(config=cfg, paths=cfg.app_paths().ensure(), config_path=tmp_path / "c.yaml")


def test_migration_0002_upgrades_v1_db(tmp_path):
    """A database created at schema v1 gains the plan columns on next open."""
    from after_scope.db.connection import _schema_files

    conn = connect(tmp_path / "old.db")
    number, _, sql = _schema_files()[0]
    assert number == 1
    from after_scope.db.connection import _statements

    with conn:
        for stmt in _statements(sql):
            conn.execute(stmt)
        conn.execute("PRAGMA user_version = 1")

    applied = apply_migrations(conn)
    assert applied == ["0002_session_plan.sql"]
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
    assert {"planned_experiment_id", "planned_strain", "planned_dir"} <= cols
    conn.close()


def test_fill_file_defaults_never_overwrites(conn):
    uid = repo.add_user(conn, "Tim de Wet", "TdW")
    sid = repo.open_session(conn, zen_pid=1)
    fid = repo.add_file(conn, sid, "/d/a.czi")
    repo.set_file_user_meta(conn, fid, strain="HAND-TYPED")
    repo.fill_file_defaults(conn, fid, user_id=uid, strain="PLAN", condition="37C")
    row = repo.get_file(conn, fid)
    assert row["strain"] == "HAND-TYPED"     # existing value wins
    assert row["condition"] == "37C"         # empty field filled
    assert row["user_id"] == uid


def test_experiment_page_declares_and_creates_dir(ctx, tmp_path):
    from after_scope.wizard.pages.declare import ExperimentPage
    from after_scope.wizard.state import WizardState

    uid = repo.list_users(ctx.db)[0]["id"]
    sid = repo.open_session(ctx.db, zen_pid=1)
    repo.set_session_user(ctx.db, sid, uid, "roster")
    state = WizardState(ctx=ctx, reason="start", session_id=sid, user_id=uid)
    page = ExperimentPage(state)
    page.on_enter()
    page.experiment.setCurrentText("efflux timelapse")
    page.strain.setText("MSM155")
    page.condition.setText("37C")
    page.save()

    row = repo.get_session(ctx.db, sid)
    assert row["planned_strain"] == "MSM155"
    assert row["planned_experiment_id"] is not None
    planned = Path(row["planned_dir"])
    assert planned.is_dir()
    # sanitized name under the first watch dir: {date}_{initials}_{experiment}
    assert planned.parent == ctx.config.watch_dirs[0].path
    assert planned.name.endswith("_efflux-timelapse") and "_" in planned.name


def test_experiment_page_skip_leaves_no_plan(ctx):
    from after_scope.wizard.pages.declare import ExperimentPage
    from after_scope.wizard.state import WizardState

    sid = repo.open_session(ctx.db, zen_pid=1)
    state = WizardState(ctx=ctx, reason="start", session_id=sid)
    page = ExperimentPage(state)
    page.on_enter()
    assert page.validate() is None  # empty is allowed
    page.save()
    row = repo.get_session(ctx.db, sid)
    assert row["planned_experiment_id"] is None and row["planned_dir"] is None


def test_same_as_last_session_prefill(ctx):
    from after_scope.wizard.pages.declare import ExperimentPage
    from after_scope.wizard.state import WizardState

    uid = repo.list_users(ctx.db)[0]["id"]
    old = repo.open_session(ctx.db, zen_pid=1)
    repo.set_session_user(ctx.db, old, uid, "roster")
    eid = repo.get_or_create_experiment(ctx.db, "prev-exp", uid)
    repo.set_session_plan(ctx.db, old, experiment_id=eid, strain="OLD1", condition="30C",
                          coverslip="pad", notes=None, planned_dir=None)

    sid = repo.open_session(ctx.db, zen_pid=2)
    repo.set_session_user(ctx.db, sid, uid, "roster")
    state = WizardState(ctx=ctx, reason="start", session_id=sid, user_id=uid)
    page = ExperimentPage(state)
    page.on_enter()
    page._prefill_last()
    assert page.experiment.currentText() == "prev-exp"
    assert page.strain.text() == "OLD1" and page.condition.text() == "30C"


def test_scanner_extra_dir(cfg, tmp_path):
    scanner = AcquisitionScanner(cfg)
    outside = tmp_path / "outside_session_dir"
    outside.mkdir()
    scanner.add_extra_dir(outside)
    # a dir already under a recursive watch root is not duplicated
    scanner.add_extra_dir(tmp_path / "watch")
    scanner.add_extra_dir(outside)
    assert scanner.extra_dirs == [outside]

    start = time.time() - 10
    f = outside / "img.czi"
    f.write_bytes(b"x")
    scanner.sweep(start)
    assert scanner.sweep(start) == [f]
    scanner.reset()
    assert scanner.extra_dirs == []
