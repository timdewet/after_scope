"""Session lifecycle operations shared by watchdog and wizard."""

from __future__ import annotations

import logging
import sqlite3

from .db import repo
from .util import now_iso

log = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, conn: sqlite3.Connection, machine: str = "", app_version: str = "") -> None:
        self.conn = conn
        self.machine = machine
        self.app_version = app_version

    # -- lifecycle ------------------------------------------------------------------

    def recover_orphans(self) -> int:
        n = repo.recover_orphans(self.conn)
        if n:
            log.warning("Recovered %d orphaned session(s) as incomplete/interrupted", n)
            repo.audit(self.conn, "orphans_recovered", count=n)
        return n

    def open(self, zen_pid: int | None) -> int:
        sid = repo.open_session(
            self.conn, zen_pid, machine=self.machine, app_version=self.app_version
        )
        repo.audit(self.conn, "zen_start", session_id=sid, zen_pid=zen_pid)
        return sid

    def close_for_zen_exit(self, session_id: int, zen_exit_code: int | None) -> None:
        reason = "zen_close" if zen_exit_code in (0, None) else "crash"
        repo.end_session(
            self.conn, session_id, ended_reason=reason, zen_exit_code=zen_exit_code
        )
        repo.audit(self.conn, "zen_exit", session_id=session_id, exit_code=zen_exit_code)

    def handover(self, session_id: int, last_activity: str | None = None) -> int:
        """User B takes over while ZEN stays open: close A's session at its last
        activity, open a fresh one. Returns the new session id."""
        old = repo.get_session(self.conn, session_id)
        repo.end_session(
            self.conn,
            session_id,
            ended_reason="handover",
            ended_at=last_activity or now_iso(),
            status="incomplete",
            incomplete_reason="handover",
        )
        new_sid = repo.open_session(
            self.conn,
            old["zen_pid"] if old else None,
            machine=self.machine,
            app_version=self.app_version,
        )
        repo.audit(self.conn, "handover", old_session=session_id, new_session=new_sid)
        return new_sid

    def auto_close_idle(self, session_id: int, last_activity: str | None = None) -> None:
        repo.end_session(
            self.conn,
            session_id,
            ended_reason="idle_timeout",
            ended_at=last_activity or now_iso(),
            status="incomplete",
            incomplete_reason="idle_timeout",
        )
        repo.audit(self.conn, "idle_timeout", session_id=session_id)

    # -- checklist outcomes ---------------------------------------------------------

    def checklist_complete(self, session_id: int) -> None:
        repo.set_session_status(self.conn, session_id, "complete")
        repo.audit(self.conn, "checklist_complete", session_id=session_id)

    def checklist_skipped(self, session_id: int, reason: str) -> None:
        repo.set_session_status(self.conn, session_id, "incomplete", incomplete_reason="skipped")
        repo.audit(self.conn, "checklist_skipped", session_id=session_id, reason=reason)

    def checklist_crashed(self, session_id: int) -> None:
        repo.set_session_status(
            self.conn, session_id, "incomplete", incomplete_reason="wizard_crash"
        )
        repo.audit(self.conn, "wizard_crash", session_id=session_id)

    # -- queries --------------------------------------------------------------------

    def open_session(self) -> sqlite3.Row | None:
        return repo.get_open_session(self.conn)

    def pending_nag(self) -> sqlite3.Row | None:
        """Oldest ended session whose checklist was never completed."""
        rows = repo.incomplete_sessions(self.conn)
        return rows[0] if rows else None
