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
        from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

        self.choice: bool | None = None
        gate = QHBoxLayout()
        gate.setSpacing(16)
        self.ok_btn = QPushButton("No problems 👍")
        self.ok_btn.setObjectName("bigYes")
        self.ok_btn.setMinimumHeight(64)
        self.ok_btn.setCheckable(True)
        self.ok_btn.clicked.connect(lambda: self._set_choice(False))
        self.problem_btn = QPushButton("Something went wrong…")
        self.problem_btn.setObjectName("bigNo")
        self.problem_btn.setMinimumHeight(64)
        self.problem_btn.setCheckable(True)
        self.problem_btn.clicked.connect(lambda: self._set_choice(True))
        gate.addWidget(self.ok_btn, stretch=1)
        gate.addWidget(self.problem_btn, stretch=1)
        self.layout_.addLayout(gate)

        self.drafts_box = QGroupBox("From your checklist answers")
        self.drafts_layout = QVBoxLayout(self.drafts_box)
        self.drafts_box.hide()
        self.layout_.addWidget(self.drafts_box)

        # the report form, revealed only after "Something went wrong…"
        self.form_box = QWidget()
        form = QVBoxLayout(self.form_box)
        form.setContentsMargins(0, 0, 0, 0)
        label = QLabel("WHAT KIND OF PROBLEM?")
        label.setObjectName("fieldLabel")
        form.addWidget(label)
        self.category = ChipGroup(list(CATEGORY_CHIPS), exclusive=True)
        form.addWidget(self.category)

        self.description = QLineEdit()
        self.description.setPlaceholderText("What happened? One line is enough.")
        form.addWidget(self.description)

        sev_label = QLabel("HOW BAD?")
        sev_label.setObjectName("fieldLabel")
        form.addWidget(sev_label)
        self.severity = ChipGroup(["minor", "major", "blocking"], exclusive=True)
        self.severity.set_value("minor")
        form.addWidget(self.severity)
        self.form_box.hide()
        self.layout_.addWidget(self.form_box)
        self.layout_.addStretch(1)
        self._draft_checks: list[tuple[QCheckBox, dict]] = []

    def _set_choice(self, problem: bool) -> None:
        self.choice = problem
        self.form_box.setVisible(problem)
        self.ok_btn.setChecked(not problem)
        self.problem_btn.setChecked(problem)

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
        if self.choice is None:
            return "Tell us whether anything went wrong this session."
        if self.choice and not self.description.text().strip():
            return "Add one line describing the problem."
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
        text = self.description.text().strip() if self.choice else ""
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
        self._set_choice(False)
