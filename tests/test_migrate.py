from __future__ import annotations

import json

from after_scope.appcontext import AppContext
from after_scope.db import repo
from after_scope.migrate.ingest import ingest_inbox
from after_scope.migrate.manifest import Manifest, ManifestFile, load_manifest


def _ctx(cfg, tmp_path):
    return AppContext(config=cfg, paths=cfg.app_paths().ensure(), config_path=tmp_path / "c.yaml")


def _manifest(ctx, tmp_path, new_name="20250101_TdW_old-exp_001.czi", **overrides):
    dest = ctx.config.dropbox.root / "MicroscopeData" / "2025" / "TdW" / new_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"migrated czi bytes")
    mf = ManifestFile(
        original_path="/legacy/old image.czi",
        new_path=str(dest),
        acquired_at="2025-01-01T10:00:00",
        strain="MSM101",
        experiment="old-exp",
        extracted={"objective_name": "63x Oil", "immersion": "Oil"},
    )
    for k, v in overrides.items():
        setattr(mf, k, v)
    m = Manifest(submitted_by="TdW", submitted_at="2026-08-14T10:00:00", files=[mf])
    return m.write(ctx.config.migrations_inbox)


def test_manifest_roundtrip(cfg, tmp_path):
    ctx = _ctx(cfg, tmp_path)
    path = _manifest(ctx, tmp_path)
    m = load_manifest(path)
    assert m.submitted_by == "TdW" and m.files[0].strain == "MSM101"
    # unique naming: a second write doesn't clobber
    path2 = _manifest(ctx, tmp_path, new_name="another.czi")
    assert path2.name != path.name or path2 != path


def test_ingest_creates_migration_rows(cfg, tmp_path):
    ctx = _ctx(cfg, tmp_path)
    _manifest(ctx, tmp_path)
    assert ingest_inbox(ctx) == 1
    row = ctx.db.execute("SELECT * FROM files WHERE origin='migration'").fetchone()
    assert row is not None
    assert row["session_id"] is None
    assert row["acquired_at"] == "2025-01-01T10:00:00"  # from CZI, not today
    assert row["strain"] == "MSM101" and row["objective_name"] == "63x Oil"
    assert row["user_id"] is not None  # matched TdW from roster
    # manifest moved to processed/ and recorded
    assert not any(ctx.config.migrations_inbox.glob("*.json"))
    assert any((ctx.config.migrations_inbox.parent / "processed").glob("*.json"))
    rec = ctx.db.execute("SELECT * FROM migration_manifests").fetchone()
    assert rec["status"] == "ingested" and rec["file_count"] == 1
    # re-ingest is a no-op (idempotent)
    assert ingest_inbox(ctx) == 0


def test_ingest_missing_target_fails_manifest(cfg, tmp_path):
    ctx = _ctx(cfg, tmp_path)
    path = _manifest(ctx, tmp_path)
    data = json.loads(path.read_text())
    data["files"][0]["new_path"] = str(tmp_path / "nope.czi")
    path.write_text(json.dumps(data))
    ingest_inbox(ctx)
    rec = ctx.db.execute("SELECT * FROM migration_manifests").fetchone()
    assert rec["status"] == "failed" and "missing" in rec["error"]
    assert any((ctx.config.migrations_inbox.parent / "failed").glob("*.json"))


def test_ingest_garbage_manifest(cfg, tmp_path):
    ctx = _ctx(cfg, tmp_path)
    ctx.config.migrations_inbox.mkdir(parents=True, exist_ok=True)
    bad = ctx.config.migrations_inbox / "manifest-x.json"
    bad.write_text("{not json")
    assert ingest_inbox(ctx) == 0
    rec = ctx.db.execute("SELECT * FROM migration_manifests").fetchone()
    assert rec["status"] == "failed"
    assert repo is not None
