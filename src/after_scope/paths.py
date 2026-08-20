"""Filesystem locations for app state (DB, logs, caches) — never inside Dropbox.

The live SQLite DB, logs and caches live on the local disk. Only derived artifacts
(CSV exports, backups, dashboard) are written into Dropbox, elsewhere in the code.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "AfterScope"


def default_data_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / APP_NAME


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path

    @property
    def db_path(self) -> Path:
        return self.data_dir / "db" / "afterscope.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def thumbs_dir(self) -> Path:
        return self.data_dir / "thumbs"

    @property
    def xml_dir(self) -> Path:
        return self.data_dir / "xml"

    @property
    def stop_flag(self) -> Path:
        return self.data_dir / "stop.flag"

    @property
    def pause_until(self) -> Path:
        # holds an ISO timestamp; the watchdog refuses to run before it passes,
        # which is what makes "pause" survive the Task Scheduler keep-alive
        return self.data_dir / "pause.until"

    @property
    def last_good_config(self) -> Path:
        return self.cache_dir / "config.last_good.yaml"

    def ensure(self) -> AppPaths:
        for d in (
            self.data_dir,
            self.db_path.parent,
            self.logs_dir,
            self.cache_dir,
            self.thumbs_dir,
            self.xml_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
        return self


def resolve_config_path(cli_arg: str | None) -> Path:
    """Locate the YAML config: CLI arg > env var > pointer file > default location.

    The pointer file (data_dir/config.path) lets install.ps1 point the app at the
    master config kept in Dropbox without hardcoding the Dropbox path.
    """
    if cli_arg:
        return Path(cli_arg).expanduser()
    env = os.environ.get("AFTER_SCOPE_CONFIG")
    if env:
        return Path(env).expanduser()
    pointer = default_data_dir() / "config.path"
    if pointer.exists():
        # utf-8-sig: tolerate a BOM (PowerShell 5.1's `-Encoding UTF8` writes one)
        target = pointer.read_text(encoding="utf-8-sig").strip().splitlines()[0]
        if target:
            return Path(target).expanduser()
    return default_data_dir() / "config.yaml"
