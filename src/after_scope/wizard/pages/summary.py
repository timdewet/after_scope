"""Final page: session recap as stat tiles. Finishing marks the checklist complete."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel

from ...db import repo
from ...util import fmt_dt, parse_iso
from ..state import EXIT_RESTART_ZEN
from ..ui.widgets import StatTile
from .base import WizardPage


class SummaryPage(WizardPage):
    title = "All done"
    short = "Done"

    def build(self) -> None:
        self.session_line = QLabel("")
        self.session_line.setObjectName("muted")
        self.layout_.addWidget(self.session_line)

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.tile_duration = StatTile("SESSION LENGTH")
        self.tile_files = StatTile("FILES CATALOGUED")
        self.tile_filed = StatTile("FILED TO DROPBOX")
        self.tile_dust = StatTile("DUST REFERENCE")
        self.tile_incidents = StatTile("PROBLEMS REPORTED")
        for tile in (self.tile_duration, self.tile_files, self.tile_filed,
                     self.tile_dust, self.tile_incidents):
            tiles.addWidget(tile)
        self.layout_.addLayout(tiles)

        footer = QLabel("Press Done — the lab dashboard and catalog update automatically.")
        footer.setObjectName("caption")
        self.layout_.addWidget(footer)
        self.layout_.addStretch(1)

        if self.state.reason == "close":
            from PySide6.QtWidgets import QPushButton

            btn = QPushButton("Actually, I'm restarting ZEN — keep my session open")
            btn.setObjectName("ghost")
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
        duration = "—"
        if row and row["started_at"] and row["ended_at"]:
            try:
                mins = int(
                    (parse_iso(row["ended_at"]) - parse_iso(row["started_at"])).total_seconds() // 60
                )
                duration = f"{mins // 60} h {mins % 60} m"
            except ValueError:
                pass
        user = repo.get_user(conn, row["user_id"]) if row and row["user_id"] else None
        self.session_line.setText(
            f"{user['full_name'] if user else 'Unknown user'} · "
            f"{fmt_dt(row['started_at']) if row else ''}"
        )
        self.tile_duration.set_value(duration)
        self.tile_files.set_value(str(len(files)))
        self.tile_filed.set_value(str(moved), good=(moved == len(files) and len(files) > 0))
        self.tile_dust.set_value("✓" if dust else "skipped", good=bool(dust))
        self.tile_incidents.set_value(str(incidents), good=(incidents == 0))

    def save(self) -> None:
        if self.state.is_end_of_session:
            self.state.sm.checklist_complete(self.state.session_id)

    def auto_fill(self) -> None:
        pass
