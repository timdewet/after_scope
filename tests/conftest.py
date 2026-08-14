from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from after_scope.config import AppConfig, RosterEntry, WatchDirCfg
from after_scope.db.connection import open_db


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = open_db(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def cfg(tmp_path: Path) -> AppConfig:
    config = AppConfig(
        watch_dirs=[WatchDirCfg(path=tmp_path / "watch")],
        roster=[
            RosterEntry(name="Tim de Wet", initials="TdW", email="tdw@example.org"),
            RosterEntry(name="Jane Doe", initials="JD"),
        ],
        data_dir=tmp_path / "data",
    )
    config.dropbox.root = tmp_path / "dropbox"
    (tmp_path / "watch").mkdir()
    config.zen.cmdline_contains = "AFTER_SCOPE_FAKE_ZEN"
    config.ui.kiosk = False
    return config
