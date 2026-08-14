"""Incident page: confirm drafts from flagged checklist items + free-text problems."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ...db import repo
from .base import WizardPage


class IncidentPage(WizardPage):
    title = "Any problems during your session?"
    short = "Problems"

    def build(self) -> None:
        self.drafts_box = QGroupBox("From your checklist answers")
        self.drafts_layout = QVBoxLayout(self.drafts_box)
        self.drafts_box.hide()
        self.layout_.addWidget(self.drafts_box)

        row = QHBoxLayout()
        self.description = QLineEdit()
        self.description.setPlaceholderText(
            "Describe any problem (focus, stage, software, damage…) — or leave empty"
        )
        self.severity = QComboBox()
        self.severity.addItems(["minor", "major", "blocking"])
        row.addWidget(self.description, stretch=1)
        row.addWidget(QLabel("Severity:"))
        row.addWidget(self.severity)
        self.layout_.addLayout(row)
        self.layout_.addStretch(1)
        self._draft_checks: list[tuple[QCheckBox, dict]] = []

    def refresh(self) -> None:
        for cb, _ in self._draft_checks:
            cb.deleteLater()
        self._draft_checks = []
        if self.state.incident_drafts:
            self.drafts_box.show()
            for draft in self.state.incident_drafts:
                cb = QCheckBox(draft["description"])
                cb.setChecked(True)
                self.drafts_layout.addWidget(cb)
                self._draft_checks.append((cb, draft))
        else:
            self.drafts_box.hide()

    def save(self) -> None:
        conn = self.state.conn
        for cb, draft in self._draft_checks:
            if cb.isChecked():
                repo.add_incident(
                    conn,
                    session_id=self.state.session_id,
                    reported_by=self.state.user_id,
                    category=draft.get("category", "problem"),
                    description=draft["description"],
                )
        text = self.description.text().strip()
        if text:
            repo.add_incident(
                conn,
                session_id=self.state.session_id,
                reported_by=self.state.user_id,
                category="problem",
                severity=self.severity.currentText(),
                description=text,
            )

    def auto_fill(self) -> None:
        pass
