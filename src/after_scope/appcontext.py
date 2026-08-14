"""AppContext bundles config + paths + DB for every entry point."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .config import AppConfig, load_config
from .db import repo
from .db.connection import open_db
from .logging_setup import setup_logging
from .paths import AppPaths, resolve_config_path

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    config: AppConfig
    paths: AppPaths
    config_path: Path
    app_version: str = __version__
    _conn: sqlite3.Connection | None = field(default=None, repr=False)

    @classmethod
    def build(cls, cli_config: str | None, role: str, with_logging: bool = True) -> AppContext:
        config_path = resolve_config_path(cli_config)
        if not config_path.exists():
            raise FileNotFoundError(
                f"Config not found: {config_path}\n"
                "Pass --config, set AFTER_SCOPE_CONFIG, or run the installer "
                "(which writes the config pointer file)."
            )
        config = load_config(config_path)
        paths = config.app_paths().ensure()
        if with_logging:
            setup_logging(paths, role)
        log.info("after_scope %s (%s) config=%s data=%s", __version__, role, config_path, paths.data_dir)
        return cls(config=config, paths=paths, config_path=config_path)

    @property
    def db(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = open_db(self.paths.db_path)
            if self.config.roster:
                repo.seed_roster(
                    self._conn, [r.model_dump() for r in self.config.roster]
                )
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
