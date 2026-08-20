"""Cleaning checklist page — rendered from the declarative checklist definition.

Each item is a full-width tappable card row: click anywhere to tick a checkbox
item, Yes/No answers are chip pairs, and a green edge marks completed rows.
Answers are prefilled from session evidence (CZI objective metadata, falling
back to the declared imaging plan) so most sessions are confirm-and-go.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ...checklist import engine
from ...config import ChecklistItemCfg
from ...db import repo
from ...util import parse_iso
from ..ui import tokens
from ..ui.widgets import ChipGroup
from .base import WizardPage


class _ItemRow(QFrame):
    """One checklist item as a card row."""

    def __init__(self, item: ChecklistItemCfg, page: CleaningPage) -> None:
        super().__init__()
        self.item = item
        self.page = page
        self.setObjectName("checkRow")
        self.setCursor(Qt.PointingHandCursor if item.type in ("checkbox", "solvent_clean")
                       else Qt.ArrowCursor)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(tokens.S4, tokens.S3, tokens.S4, tokens.S3)
        outer.setSpacing(tokens.S1)
        row = QHBoxLayout()
        row.setSpacing(tokens.S3)

        if item.type in ("checkbox", "solvent_clean"):
            label_text = item.label
            if item.type == "solvent_clean":
                label_text = f"{item.label} ({page.state.cfg.solvent.approved_solvent})"
            self.check = QCheckBox(label_text)
            self.check.toggled.connect(self._changed)
            row.addWidget(self.check, stretch=1)
            if item.type == "solvent_clean":
                obj_label = QLabel("Objective:")
                obj_label.setObjectName("muted")
                self.objective = QComboBox()
                self.objective.setEditable(True)
                row.addWidget(obj_label)
                row.addWidget(self.objective)
        elif item.type == "yes_no":
            label = QLabel(item.label)
            label.setObjectName("rowLabel")
            label.setWordWrap(True)
            row.addWidget(label, stretch=1)
            self.chips = ChipGroup(["Yes", "No"], exclusive=True, on_change=self._changed)
            row.addWidget(self.chips)
        elif item.type == "select":
            label = QLabel(item.label)
            label.setObjectName("rowLabel")
            row.addWidget(label, stretch=1)
            self.combo = QComboBox()
            self.combo.addItems([""] + item.options)
            self.combo.currentTextChanged.connect(self._changed)
            row.addWidget(self.combo)
        elif item.type == "number":
            label = QLabel(item.label)
            label.setObjectName("rowLabel")
            row.addWidget(label, stretch=1)
            self.spin = QDoubleSpinBox()
            row.addWidget(self.spin)
        elif item.type == "text":
            label = QLabel(item.label)
            label.setObjectName("rowLabel")
            row.addWidget(label, stretch=1)
            self.edit = QLineEdit()
            self.edit.setMinimumWidth(280)
            row.addWidget(self.edit)
        outer.addLayout(row)

        if item.help:
            help_label = QLabel(item.help)
            help_label.setWordWrap(True)
            help_label.setObjectName("caption")
            outer.addWidget(help_label)
        if item.type == "solvent_clean":
            self.last_label = QLabel("")
            self.last_label.setObjectName("caption")
            outer.addWidget(self.last_label)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        # the whole card is the tap target for tick-style items
        if self.item.type in ("checkbox", "solvent_clean"):
            self.check.toggle()
        event.accept()

    def _changed(self, *_args) -> None:
        self._refresh_done()
        self.page.re_evaluate()

    def _refresh_done(self) -> None:
        done = self._is_done()
        if self.property("done") != ("true" if done else "false"):
            self.setProperty("done", "true" if done else "false")
            style = self.style()
            style.unpolish(self)
            style.polish(self)

    def _is_done(self) -> bool:
        value = self.value()
        if self.item.type in ("checkbox",):
            return value is True
        if self.item.type == "solvent_clean":
            return bool(value and value.get("done"))
        if self.item.type == "yes_no":
            return value is not None
        return value not in (None, "", 0.0)

    # -- value access ---------------------------------------------------------------

    def value(self) -> Any:
        t = self.item.type
        if t == "checkbox":
            return self.check.isChecked()
        if t == "yes_no":
            picked = self.chips.value()
            if picked == "Yes":
                return True
            if picked == "No":
                return False
            return None
        if t == "select":
            return self.combo.currentText() or None
        if t == "number":
            return self.spin.value()
        if t == "text":
            return self.edit.text().strip() or None
        if t == "solvent_clean":
            if not self.check.isChecked():
                return {"done": False}
            return {"done": True, "objective": self.objective.currentText().strip()}
        return None

    def set_value(self, value: Any) -> None:
        t = self.item.type
        if t == "checkbox" and isinstance(value, bool):
            self.check.setChecked(value)
        elif t == "yes_no" and isinstance(value, bool):
            self.chips.set_value("Yes" if value else "No")
        elif t == "solvent_clean" and isinstance(value, dict):
            self.check.setChecked(bool(value.get("done")))
        self._refresh_done()


class CleaningPage(WizardPage):
    title = "Cleaning & shutdown checklist"
    short = "Cleaning"

    def build(self) -> None:
        hint = QLabel(
            "Answers are prefilled from your session where possible — confirm and go."
        )
        hint.setObjectName("caption")
        self.layout_.addWidget(hint)
        self.items = engine.load_items(self.state.cfg)
        self.widgets: dict[str, _ItemRow] = {}
        for item in self.items:
            w = _ItemRow(item, self)
            self.widgets[item.key] = w
            self.layout_.addWidget(w)
        self.layout_.addStretch(1)

    def refresh(self) -> None:
        pre = engine.prefill(self.state.conn, self.state.session_id, self.state.cfg, self.items)
        for key, value in pre.items():
            self.widgets[key].set_value(value)
        self._refresh_solvent_info()
        self.re_evaluate()

    def _declared_objectives(self) -> list[str]:
        """Objective tokens from the declared imaging plan (e.g. '100x oil')."""
        row = repo.get_session(self.state.conn, self.state.session_id)
        imaging = (row["planned_imaging"] or "") if row else ""
        return re.findall(r"\b\d+x(?:\s*oil)?\b", imaging, flags=re.IGNORECASE)

    def _refresh_solvent_info(self) -> None:
        for w in self.widgets.values():
            if w.item.type != "solvent_clean":
                continue
            oils = repo.session_oil_objectives(self.state.conn, self.state.session_id)
            options = oils or self._declared_objectives() or [self.state.cfg.dust.objective]
            w.objective.clear()
            w.objective.addItems(options)
            last = repo.last_solvent_clean(self.state.conn)
            suggest = self.state.cfg.solvent.suggest_after_days
            if last:
                try:
                    days = (datetime.now() - parse_iso(last["created_at"])).days
                    w.last_label.setText(
                        f"Last solvent clean: {days} day(s) ago (suggested: every {suggest} days)."
                    )
                except ValueError:
                    w.last_label.setText("")
            else:
                w.last_label.setText(
                    f"No solvent clean on record yet (suggested: every {suggest} days)."
                )

    def responses(self) -> dict[str, Any]:
        return {key: w.value() for key, w in self.widgets.items()}

    def re_evaluate(self) -> None:
        responses = self.responses()
        visible = {i.key for i in engine.visible_items(self.items, responses)}
        for key, w in self.widgets.items():
            w.setVisible(key in visible)
            w._refresh_done()

    def validate(self) -> str | None:
        missing = engine.missing_required(self.items, self.responses())
        if missing:
            return "Still needed: " + "; ".join(i.label for i in missing)
        return None

    def save(self) -> None:
        conn = self.state.conn
        responses = self.responses()
        flagged = engine.save_responses(conn, self.state.session_id, self.items, responses)
        for item in flagged:
            self.state.incident_drafts.append(
                {
                    "category": "problem",
                    "description": f"Checklist flag: {item.label} -> {responses.get(item.key)!r}",
                }
            )
        for item in self.items:
            if item.type != "solvent_clean":
                continue
            value = responses.get(item.key)
            if isinstance(value, dict) and value.get("done"):
                repo.add_maintenance_event(
                    conn,
                    "solvent_clean",
                    objective_name=value.get("objective") or None,
                    solvent=self.state.cfg.solvent.approved_solvent,
                    session_id=self.state.session_id,
                    user_id=self.state.user_id,
                )

    def auto_fill(self) -> None:
        # fill required items sensibly; leave optional ones (e.g. solvent) untouched
        for _ in range(3):  # visibility changes as answers land
            responses = self.responses()
            for item in engine.missing_required(self.items, responses):
                w = self.widgets[item.key]
                if item.type == "checkbox":
                    w.check.setChecked(True)
                elif item.type == "yes_no":
                    prefill = responses.get(item.key)
                    w.set_value(prefill if isinstance(prefill, bool) else True)
                elif item.type == "select" and item.options:
                    w.combo.setCurrentIndex(1)
                elif item.type == "text":
                    w.edit.setText("-")
