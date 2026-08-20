from __future__ import annotations

import json
from pathlib import Path

import pytest

from after_scope.appcontext import AppContext
from after_scope.db import repo
from after_scope.session import SessionManager
from after_scope.watchdog.ingest import ingest_stable_file
from after_scope.wizard.app import run_wizard
from after_scope.wizard.controller import WizardWindow, build_pages
from after_scope.wizard.state import EXIT_COMPLETE, EXIT_HANDOVER, WizardState

pytest.importorskip("PySide6")


@pytest.fixture(autouse=True)
def _ensure_qapp(qapp):
    """Widgets are constructed in every test here; a QApplication must exist first."""
    yield


@pytest.fixture
def ctx(cfg, tmp_path):
    return AppContext(config=cfg, paths=cfg.app_paths().ensure(), config_path=tmp_path / "c.yaml")


def _make_session_with_files(ctx, tmp_path, with_dust=True):
    sm = SessionManager(ctx.db, app_version="test")
    sid = sm.open(zen_pid=42)
    watch = tmp_path / "watch"
    names = ["Snap-1.czi", "Snap-2.czi"] + (["dustref_end.czi"] if with_dust else [])
    for name in names:
        p = watch / name
        p.write_bytes(b"fake-czi-" + name.encode())
        ingest_stable_file(ctx.db, ctx.config, ctx.paths, sid, p)
    sm.close_for_zen_exit(sid, 0)
    return sid


def test_build_pages_composition(ctx):
    sm = SessionManager(ctx.db)
    sid = sm.open(zen_pid=1)

    state = WizardState(ctx=ctx, reason="close", session_id=sid)
    names = [type(p).__name__ for p in build_pages(state)]
    assert names == ["UserPage", "FilesPage", "NamingPage", "CleaningPage",
                     "DustPage", "IncidentPage", "SummaryPage"]

    ctx.config.dust.required = "off"
    names = [type(p).__name__ for p in build_pages(WizardState(ctx=ctx, reason="close", session_id=sid))]
    assert "DustPage" not in names
    ctx.config.dust.required = "prompt"

    names = [type(p).__name__ for p in build_pages(WizardState(ctx=ctx, reason="start", session_id=sid))]
    assert names == ["UserPage", "ExperimentPage", "ArrivalPage", "IssuesPage", "SavingPage"]

    ctx.config.declare.enabled = False
    names = [type(p).__name__ for p in build_pages(WizardState(ctx=ctx, reason="start", session_id=sid))]
    assert "ExperimentPage" not in names
    ctx.config.declare.enabled = True

    names = [type(p).__name__ for p in build_pages(WizardState(ctx=ctx, reason="declare", session_id=sid))]
    assert names == ["ExperimentPage"]

    # a pending nag adds the offer page to the pre-use flow
    old = sm.open(zen_pid=0)
    sm.close_for_zen_exit(old, 0)
    names = [type(p).__name__ for p in build_pages(WizardState(ctx=ctx, reason="start", session_id=sid))]
    assert names[-2] == "NagOfferPage" and names[-1] == "SavingPage"


def test_end_of_session_auto_flow(ctx, tmp_path):
    sid = _make_session_with_files(ctx, tmp_path)
    code = run_wizard(ctx, sid, "close", auto_accept=True)
    assert code == EXIT_COMPLETE

    row = repo.get_session(ctx.db, sid)
    assert row["status"] == "complete" and row["user_id"] is not None

    files = repo.session_files(ctx.db, sid)
    moved = [f for f in files if f["status"] == "moved"]
    assert len(moved) == 2
    for f in moved:
        assert Path(f["current_path"]).exists()
        assert "MicroscopeData" in f["current_path"]
        assert f["strain"] == "TEST1" and f["condition"] == "ctrl"

    # checklist persisted, dust ref registered from the dustref_ file
    responses = {r["item_key"]: json.loads(r["response_json"])
                 for r in repo.checklist_responses(ctx.db, sid)}
    assert responses["stage_clean"] is True and responses["dust_cover"] is True
    ref = repo.session_dust_ref(ctx.db, sid)
    assert ref is not None and ref["method"] == "manual"
    # the dust file was filed into the dustrefs tree
    dust_file = repo.get_file(ctx.db, ref["file_id"])
    assert "dustrefs" in dust_file["current_path"]


def test_end_of_session_without_dust_logs_skip(ctx, tmp_path):
    sid = _make_session_with_files(ctx, tmp_path, with_dust=False)
    code = run_wizard(ctx, sid, "close", auto_accept=True)
    assert code == EXIT_COMPLETE
    refs = repo.dust_refs(ctx.db)
    assert len(refs) == 1 and refs[0]["method"] == "skipped"


def test_preuse_auto_flow_sets_user_and_arrival(ctx):
    sm = SessionManager(ctx.db)
    sid = sm.open(zen_pid=7)
    code = run_wizard(ctx, sid, "start", auto_accept=True)
    assert code == EXIT_COMPLETE
    row = repo.get_session(ctx.db, sid)
    assert row["user_id"] is not None
    assert row["arrival_state_ok"] == 1
    assert row["status"] == "open"  # pre-use never closes the session


def test_whoami_takeover_extends_and_exits_handover(ctx, qtbot):
    sm = SessionManager(ctx.db)
    sid = sm.open(zen_pid=7)
    users = repo.list_users(ctx.db)
    repo.set_session_user(ctx.db, sid, users[0]["id"], "roster")

    state = WizardState(ctx=ctx, reason="whoami", session_id=sid)
    win = WizardWindow(state)
    qtbot.addWidget(win)
    whoami = win.pages[0]
    whoami.on_enter()
    assert users[0]["full_name"] in whoami.still_btn.text()

    whoami._take_over(users[1]["id"])  # handover to the second roster user
    # continue through the appended pre-use pages automatically
    guard = 0
    while not win._finishing and guard < 10:
        guard += 1
        page = win.pages[win.index]
        page.on_enter()
        page.auto_fill()
        win.next_clicked()
    assert state.exit_code == EXIT_HANDOVER
    old = repo.get_session(ctx.db, sid)
    assert old["incomplete_reason"] == "handover"
    new = repo.get_open_session(ctx.db)
    assert new is not None and new["user_id"] == users[1]["id"]


def test_retro_checklist_from_nag_offer(ctx, qtbot):
    sm = SessionManager(ctx.db)
    old_sid = sm.open(zen_pid=1)
    sm.close_for_zen_exit(old_sid, 0)  # incomplete -> nag pending
    current = sm.open(zen_pid=2)

    state = WizardState(ctx=ctx, reason="start", session_id=current)
    win = WizardWindow(state)
    qtbot.addWidget(win)
    guard = 0
    while not win._finishing and guard < 20:
        guard += 1
        page = win.pages[win.index]
        page.on_enter()
        if type(page).__name__ == "NagOfferPage":
            page._do_now()  # user opts to complete the old checklist now
            continue
        page.auto_fill()
        win.next_clicked()
    assert repo.get_session(ctx.db, old_sid)["status"] == "complete"
    assert repo.get_session(ctx.db, current)["status"] == "open"


def test_annotate_toast_applies_edits(ctx, qtbot):
    from after_scope.wizard.toast import AnnotateToast

    sm = SessionManager(ctx.db)
    sid = sm.open(zen_pid=1)
    uid = repo.list_users(ctx.db)[0]["id"]
    repo.set_session_user(ctx.db, sid, uid, "roster")
    f1 = repo.add_file(ctx.db, sid, "/d/Snap-1.czi")
    f2 = repo.add_file(ctx.db, sid, "/d/Snap-2.czi")

    toast = AnnotateToast(ctx, sid, [f1, f2], timeout_seconds=60)
    qtbot.addWidget(toast)
    toast._expand()
    toast.experiment.setText("corrected-exp")
    toast.strain.setText("MSM200")
    toast._apply()

    for fid in (f1, f2):
        row = repo.get_file(ctx.db, fid)
        assert row["strain"] == "MSM200"
        assert row["experiment_id"] is not None
    exp = ctx.db.execute("SELECT name FROM experiments WHERE id=?",
                         (repo.get_file(ctx.db, f1)["experiment_id"],)).fetchone()
    assert exp["name"] == "corrected-exp"


def test_found_dirty_creates_attributed_incident(ctx, qtbot):
    sm = SessionManager(ctx.db)
    prev_sid = sm.open(zen_pid=1)
    sm.close_for_zen_exit(prev_sid, 0)
    sm.checklist_complete(prev_sid)
    sid = sm.open(zen_pid=2)

    state = WizardState(ctx=ctx, reason="start", session_id=sid)
    win = WizardWindow(state)
    qtbot.addWidget(win)
    # advance through user + experiment pages
    while type(win.pages[win.index]).__name__ != "ArrivalPage":
        page = win.pages[win.index]
        page.on_enter()
        page.auto_fill()
        win.next_clicked()
    # arrival page: report found-dirty
    arrival = win.pages[win.index]
    arrival.on_enter()
    arrival._set_choice(False)
    arrival.category_checks["found_sample"].setChecked(True)
    arrival.note.setText("slide left on the stage")
    win.next_clicked()

    incidents = repo.open_incidents(ctx.db)
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc["category"] == "found_sample"
    assert inc["attributed_session_id"] == prev_sid
    assert repo.get_session(ctx.db, sid)["arrival_state_ok"] == 0
