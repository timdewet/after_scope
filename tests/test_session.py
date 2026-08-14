from __future__ import annotations

from after_scope.db import repo
from after_scope.dustref import record_skip, register_session_dust_refs
from after_scope.session import SessionManager


def test_zen_close_vs_crash(conn):
    sm = SessionManager(conn, app_version="0.1.0")
    s1 = sm.open(zen_pid=10)
    sm.close_for_zen_exit(s1, zen_exit_code=0)
    assert repo.get_session(conn, s1)["ended_reason"] == "zen_close"

    s2 = sm.open(zen_pid=11)
    sm.close_for_zen_exit(s2, zen_exit_code=1)
    assert repo.get_session(conn, s2)["ended_reason"] == "crash"


def test_handover_splits_at_last_activity(conn):
    sm = SessionManager(conn)
    s1 = sm.open(zen_pid=10)
    new = sm.handover(s1, last_activity="2026-08-14T12:00:00")
    old = repo.get_session(conn, s1)
    assert old["status"] == "incomplete" and old["incomplete_reason"] == "handover"
    assert old["ended_at"] == "2026-08-14T12:00:00"
    fresh = repo.get_session(conn, new)
    assert fresh["status"] == "open" and fresh["zen_pid"] == 10


def test_idle_timeout(conn):
    sm = SessionManager(conn)
    s1 = sm.open(zen_pid=10)
    sm.auto_close_idle(s1, last_activity="2026-08-14T02:00:00")
    row = repo.get_session(conn, s1)
    assert row["ended_reason"] == "idle_timeout" and row["status"] == "incomplete"


def test_nag_queue_order_and_completion(conn):
    sm = SessionManager(conn)
    s1 = sm.open(zen_pid=1)
    sm.close_for_zen_exit(s1, 0)  # awaiting_checklist -> nag queue
    s2 = sm.open(zen_pid=2)
    sm.close_for_zen_exit(s2, 0)
    assert sm.pending_nag()["id"] == s1
    sm.checklist_complete(s1)
    assert sm.pending_nag()["id"] == s2
    sm.checklist_skipped(s2, "in a hurry")
    row = repo.get_session(conn, s2)
    assert row["incomplete_reason"] == "skipped"
    assert sm.pending_nag()["id"] == s2  # skipped sessions stay in the queue


def test_dust_ref_registration_idempotent(conn):
    sm = SessionManager(conn)
    sid = sm.open(zen_pid=1)
    fid = repo.add_file(conn, sid, "/d/dustref_1.czi", status="new")
    repo.set_file_status(conn, fid, "dust_ref")
    repo.set_file_metadata(conn, fid, {"objective_name": "100x Oil"})
    assert len(register_session_dust_refs(conn, sid)) == 1
    assert register_session_dust_refs(conn, sid) == []
    ref = repo.session_dust_ref(conn, sid)
    assert ref["objective_name"] == "100x Oil" and ref["method"] == "manual"


def test_dust_skip_only_when_no_real_ref(conn):
    sm = SessionManager(conn)
    sid = sm.open(zen_pid=1)
    record_skip(conn, sid, "forgot")
    rows = repo.dust_refs(conn)
    assert len(rows) == 1 and rows[0]["method"] == "skipped"
    # a real ref exists in another session; skip there is still recorded independently
    sid2 = sm.open(zen_pid=2)
    fid = repo.add_file(conn, sid2, "/d/dustref_2.czi")
    repo.set_file_status(conn, fid, "dust_ref")
    register_session_dust_refs(conn, sid2)
    record_skip(conn, sid2)  # no-op: session already has a real ref
    methods = [r["method"] for r in repo.dust_refs(conn)]
    assert methods.count("skipped") == 1
