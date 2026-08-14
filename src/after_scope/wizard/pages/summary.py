"""Final page: session recap. Finishing marks the checklist complete."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

from ...db import repo
from ...util import fmt_dt, parse_iso
from ..state import EXIT_RESTART_ZEN
from .base import WizardPage


class SummaryPage(WizardPage):
    title = "All done"

    def build(self) -> None:
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.layout_.addWidget(self.body)
        self.layout_.addStretch(1)
        if self.state.reason == "close":
            from PySide6.QtWidgets import QPushButton

            btn = QPushButton("Actually, I'm restarting ZEN — keep my session open")
            btn.clicked.connect(lambda: self.controller.finish(EXIT_RESTART_ZEN))
            self.layout_.addWidget(btn)

    def refresh(self) -> None:
        conn = self.state.conn
        sid = self.state.session_id
        row = repo.get_session(conn, sid)
        files = [f for f in repo.session_files(conn, sid) if f["status"] != "excluded"]
        moved = sum(1 for f in files if f["status"] in ("moved", "copied"))
        dust = repo.session_dust_ref(conn, sid)
        incidents = conn.execute(
            "SELECT COUNT(*) c FROM incidents WHERE session_id=?", (sid,)
        ).fetchone()["c"]
        duration = ""
        if row and row["started_at"] and row["ended_at"]:
            try:
                mins = int(
                    (parse_iso(row["ended_at"]) - parse_iso(row["started_at"])).total_seconds() // 60
                )
                duration = f"{mins // 60} h {mins % 60} m"
            except ValueError:
                pass
        user = repo.get_user(conn, row["user_id"]) if row and row["user_id"] else None
        lines = [
            f"Session: {fmt_dt(row['started_at']) if row else ''}"
            + (f" — {duration}" if duration else ""),
            f"User: {user['full_name'] if user else 'unknown'}",
            f"Files catalogued: {len(files)} ({moved} filed into the Dropbox tree)",
            f"Dust reference: {'✓' if dust else 'skipped (logged)'}",
            f"Incidents reported: {incidents}",
            "",
            "Press Done — the lab dashboard and catalog update automatically.",
        ]
        self.body.setText("\n".join(lines))

    def save(self) -> None:
        if self.state.is_end_of_session:
            self.state.sm.checklist_complete(self.state.session_id)

    def auto_fill(self) -> None:
        pass
