"""Shared mutable state threaded through the wizard pages."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from ..appcontext import AppContext
from ..config import AppConfig
from ..session import SessionManager

END_REASONS = {"close", "crash", "nag"}
PREUSE_REASONS = {"start", "handover"}

EXIT_COMPLETE = 0
EXIT_ERROR = 1
EXIT_SKIPPED = 2
EXIT_RESTART_ZEN = 3
EXIT_HANDOVER = 4


@dataclass
class WizardState:
    ctx: AppContext
    reason: str
    session_id: int
    user_id: int | None = None
    handover_happened: bool = False
    incident_drafts: list[dict] = field(default_factory=list)
    exit_code: int = EXIT_COMPLETE

    @property
    def cfg(self) -> AppConfig:
        return self.ctx.config

    @property
    def conn(self) -> sqlite3.Connection:
        return self.ctx.db

    @property
    def sm(self) -> SessionManager:
        return SessionManager(self.conn, app_version=self.ctx.app_version)

    @property
    def is_end_of_session(self) -> bool:
        return self.reason in END_REASONS
