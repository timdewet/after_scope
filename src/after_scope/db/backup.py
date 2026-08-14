"""Nightly consistent DB snapshot into Dropbox, with retention pruning."""

from __future__ import annotations

import logging
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

RETENTION_DAYS = 60


def backup_db(conn: sqlite3.Connection, backup_dir: Path, now: datetime | None = None) -> Path | None:
    now = now or datetime.now()
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log.error("Cannot create backup dir %s", backup_dir, exc_info=True)
        return None
    dest = backup_dir / f"afterscope-{now:%Y%m%d}.db"
    try:
        with tempfile.TemporaryDirectory() as td:
            local = Path(td) / "snapshot.db"
            snap = sqlite3.connect(local)
            try:
                conn.backup(snap)  # consistent snapshot even mid-write
            finally:
                snap.close()
            shutil.copyfile(local, dest)
    except (sqlite3.Error, OSError):
        log.error("DB backup failed", exc_info=True)
        return None
    _prune(backup_dir, now)
    return dest


def _prune(backup_dir: Path, now: datetime) -> None:
    cutoff = now - timedelta(days=RETENTION_DAYS)
    for f in backup_dir.glob("afterscope-*.db"):
        try:
            stamp = datetime.strptime(f.stem.split("-")[1], "%Y%m%d")
            if stamp < cutoff:
                f.unlink()
        except (ValueError, OSError):
            continue
