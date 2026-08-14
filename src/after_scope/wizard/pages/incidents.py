"""Incident page: confirm drafts from flagged checklist items + structured report."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ...db import repo
from ..ui.widgets import ChipGroup
from .base import WizardPage

CATEGORY_CHIPS = {
    "Focus / optics": "focus_optics",
    "Stage": "stage",
    "Objective damage": "objective_damage",
    "Software / ZEN": "software",
    "Spill or mess": "spill",
    "Other": "problem",
}


class IncidentPage(WizardPage):
    title = "Any problems during your session?"
    short = "Problems"

    def build(self) -> None:
        hint = QLabel("Leave everything empty if the session was uneventful.")
        hint.setObjectName("caption")
        self.layout_.addWidget(hint)

        self.drafts_box = QGroupBox("From your checklist answers")
        self.drafts_layout = QVBoxLayout(self.drafts_box)
        self.drafts_box.hide()
        self.layout_.addWidget(self.drafts_box)

        label = QLabel("WHAT KIND OF PROBLEM?")
        label.setObjectName("fieldLabel")
        self.layout_.addWidget(label)
        self.category = ChipGroup(list(CATEGORY_CHIPS), exclusive=True)
        self.layout_.addWidget(self.category)

        self.description = QLineEdit()
        self.description.setPlaceholderText("What happened? One line is enough.")
        self.layout_.addWidget(self.description)

        sev_label = QLabel("HOW BAD?")
        sev_label.setObjectName("fieldLabel")
        self.layout_.addWidget(sev_label)
        self.severity = ChipGroup(["minor", "major", "blocking"], exclusive=True)
        self.severity.set_value("minor")
        self.layout_.addWidget(self.severity)
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

    def validate(self) -> str | None:
        if self.category.value() and not self.description.text().strip():
            return "Add one line describing the problem (or unselect the category)."
        return None

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
            category = CATEGORY_CHIPS.get(self.category.value() or "Other", "problem")
            repo.add_incident(
                conn,
                session_id=self.state.session_id,
                reported_by=self.state.user_id,
                category=category,
                severity=self.severity.value() or "minor",
                description=text,
            )

    def auto_fill(self) -> None:
        pass
