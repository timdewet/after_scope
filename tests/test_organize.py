from __future__ import annotations

from after_scope.db import repo
from after_scope.metadata.organize import execute_plans, plan_moves, undo_move


def _setup_session(conn, cfg, tmp_path, n=2):
    uid = repo.add_user(conn, "Tim de Wet", "TdW")
    sid = repo.open_session(conn, zen_pid=1)
    repo.set_session_user(conn, sid, uid, "roster")
    eid = repo.get_or_create_experiment(conn, "efflux-timelapse", uid)
    fids = []
    src_dir = tmp_path / "watch"
    src_dir.mkdir(exist_ok=True)
    for i in range(n):
        p = src_dir / f"Image {i}.czi"
        p.write_bytes(b"czi-bytes-%d" % i)
        fid = repo.add_file(conn, sid, str(p), size_bytes=p.stat().st_size)
        repo.set_file_metadata(conn, fid, {"acquired_at": "2026-08-14T13:00:00"})
        repo.set_file_user_meta(
            conn, fid, experiment_id=eid, user_id=uid, strain="MSM155", condition="37C"
        )
        fids.append(fid)
    return sid, fids


def test_plan_and_execute_move(conn, cfg, tmp_path):
    sid, fids = _setup_session(conn, cfg, tmp_path)
    plans = plan_moves(conn, sid, cfg)
    assert len(plans) == 2
    names = [p.dst.name for p in plans]
    assert names == [
        "20260814_TdW_efflux-timelapse_MSM155_37C_001.czi",
        "20260814_TdW_efflux-timelapse_MSM155_37C_002.czi",
    ]
    results = execute_plans(conn, plans)
    assert set(results.values()) == {"moved"}
    for p in plans:
        assert p.dst.exists() and not p.src.exists()
    row = repo.get_file(conn, fids[0])
    assert row["status"] == "moved" and row["current_path"] == str(plans[0].dst)
    # original path retained for provenance
    assert row["original_path"].endswith("Image 0.czi")


def test_excluded_and_index_only(conn, cfg, tmp_path):
    sid, fids = _setup_session(conn, cfg, tmp_path)
    repo.set_file_status(conn, fids[0], "excluded")
    cfg.organize.mode = "index_only"
    plans = plan_moves(conn, sid, cfg)
    assert len(plans) == 1 and plans[0].action == "index_only"
    results = execute_plans(conn, plans)
    assert results == {fids[1]: "indexed"}
    assert repo.get_file(conn, fids[1])["status"] == "indexed"


def test_missing_source_marked(conn, cfg, tmp_path):
    sid, fids = _setup_session(conn, cfg, tmp_path, n=1)
    import os

    os.remove(repo.get_file(conn, fids[0])["current_path"])
    plans = plan_moves(conn, sid, cfg)
    results = execute_plans(conn, plans)
    assert results[fids[0]] == "missing"


def test_dust_ref_goes_to_dustrefs_tree(conn, cfg, tmp_path):
    sid, fids = _setup_session(conn, cfg, tmp_path, n=1)
    repo.set_file_status(conn, fids[0], "dust_ref")
    plans = plan_moves(conn, sid, cfg)
    assert "dustrefs" in str(plans[0].dst)
    assert plans[0].dst.name.startswith("dustref_20260814")
    execute_plans(conn, plans)
    assert repo.get_file(conn, fids[0])["status"] == "dust_ref"  # status preserved
    assert plans[0].dst.exists()


def test_undo_move(conn, cfg, tmp_path):
    sid, fids = _setup_session(conn, cfg, tmp_path, n=1)
    plans = plan_moves(conn, sid, cfg)
    execute_plans(conn, plans)
    move = conn.execute("SELECT * FROM file_moves WHERE file_id=?", (fids[0],)).fetchone()
    assert undo_move(conn, move["id"]) is True
    row = repo.get_file(conn, fids[0])
    assert row["current_path"].endswith("Image 0.czi")
    assert __import__("pathlib").Path(row["current_path"]).exists()
    assert not plans[0].dst.exists()
    # can't undo twice
    assert undo_move(conn, move["id"]) is False


def test_never_overwrites(conn, cfg, tmp_path):
    sid, fids = _setup_session(conn, cfg, tmp_path, n=1)
    plans = plan_moves(conn, sid, cfg)
    plans[0].dst.parent.mkdir(parents=True, exist_ok=True)
    plans[0].dst.write_bytes(b"precious existing data")
    results = execute_plans(conn, plans)
    assert results[fids[0]] == "move_failed"
    assert plans[0].dst.read_bytes() == b"precious existing data"
    assert plans[0].src.exists()  # source untouched
