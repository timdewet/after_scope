from __future__ import annotations

import json

from after_scope.db import repo
from after_scope.db.connection import apply_migrations, open_db
from after_scope.db.export_csv import export_all


def test_migrations_idempotent(tmp_path):
    conn = open_db(tmp_path / "m.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] >= 1
    assert apply_migrations(conn) == []  # second run: nothing to do
    conn.close()


def test_roster_seed_idempotent(conn):
    roster = [{"name": "Tim de Wet", "initials": "TdW", "email": None}]
    assert repo.seed_roster(conn, roster) == 1
    assert repo.seed_roster(conn, roster) == 0
    users = repo.list_users(conn)
    assert len(users) == 1 and users[0]["full_name"] == "Tim de Wet"


def test_session_lifecycle_and_nag_queue(conn):
    uid = repo.add_user(conn, "Jane Doe", "JD")
    sid = repo.open_session(conn, zen_pid=123, app_version="0.1.0")
    repo.set_session_user(conn, sid, uid, "roster")
    assert repo.get_open_session(conn)["id"] == sid

    repo.end_session(conn, sid, ended_reason="zen_close", zen_exit_code=0)
    assert repo.get_session(conn, sid)["status"] == "awaiting_checklist"
    assert [s["id"] for s in repo.incomplete_sessions(conn)] == [sid]

    repo.set_session_status(conn, sid, "complete")
    row = repo.get_session(conn, sid)
    assert row["status"] == "complete" and row["checklist_completed_at"]
    assert repo.incomplete_sessions(conn) == []


def test_orphan_recovery(conn):
    sid = repo.open_session(conn, zen_pid=1)
    assert repo.recover_orphans(conn) == 1
    row = repo.get_session(conn, sid)
    assert row["status"] == "incomplete" and row["incomplete_reason"] == "interrupted"
    assert row["ended_at"]


def test_files_and_oil_detection(conn):
    sid = repo.open_session(conn, zen_pid=1)
    fid = repo.add_file(conn, sid, "/data/a.czi", size_bytes=100)
    # duplicate add returns the same row
    assert repo.add_file(conn, sid, "/data/a.czi") == fid
    repo.set_file_metadata(
        conn,
        fid,
        {"objective_name": "Plan-Apochromat 100x/1.4 Oil", "immersion": "Oil", "na": 1.4},
    )
    assert repo.session_oil_objectives(conn, sid) == ["Plan-Apochromat 100x/1.4 Oil"]
    repo.set_file_user_meta(conn, fid, strain="MSM155", condition="37C")
    row = repo.get_file(conn, fid)
    assert row["strain"] == "MSM155" and row["na"] == 1.4


def test_checklist_upsert(conn):
    sid = repo.open_session(conn, zen_pid=1)
    repo.save_checklist_response(conn, sid, "stage_clean", "Stage wiped", True)
    repo.save_checklist_response(conn, sid, "stage_clean", "Stage wiped", False, flagged=True)
    rows = repo.checklist_responses(conn, sid)
    assert len(rows) == 1
    assert json.loads(rows[0]["response_json"]) is False and rows[0]["flagged"] == 1


def test_maintenance_and_incidents(conn):
    uid = repo.add_user(conn, "Jane Doe", "JD")
    sid = repo.open_session(conn, zen_pid=1)
    repo.add_maintenance_event(
        conn, "solvent_clean", objective_name="100x Oil", solvent="ethanol", user_id=uid
    )
    last = repo.last_solvent_clean(conn, "100x Oil")
    assert last["solvent"] == "ethanol"
    assert repo.last_solvent_clean(conn, "63x") is None

    iid = repo.add_incident(
        conn, session_id=sid, category="found_sample", description="slide left on stage",
        reported_by=uid,
    )
    assert len(repo.open_incidents(conn)) == 1
    repo.resolve_incident(conn, iid, resolved_by=uid)
    assert repo.open_incidents(conn) == []


def test_export_all_writes_csvs(conn, tmp_path):
    uid = repo.add_user(conn, "Jane Doe", "JD")
    sid = repo.open_session(conn, zen_pid=1)
    repo.set_session_user(conn, sid, uid, "roster")
    repo.add_file(conn, sid, "/data/a.czi")
    out = tmp_path / "exports"
    written = export_all(conn, out)
    names = {p.name for p in written}
    assert {"sessions.csv", "files_catalog.csv", "cleaning_log.csv",
            "maintenance.csv", "incidents.csv", "dust_refs.csv"} <= names
    text = (out / "sessions.csv").read_text(encoding="utf-8-sig")
    assert "Jane Doe" in text
    assert (out / "README.txt").exists()


def test_previous_session_attribution(conn):
    s1 = repo.open_session(conn, zen_pid=1)
    repo.end_session(conn, s1, ended_reason="zen_close")
    s2 = repo.open_session(conn, zen_pid=2)
    prev = repo.previous_session(conn, s2)
    assert prev["id"] == s1
