"""Cleaning checklist page — rendered from the declarative checklist definition."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ...checklist import engine
from ...config import ChecklistItemCfg
from ...db import repo
from ...util import parse_iso
from .base import WizardPage


class _ItemWidget(QWidget):
    def __init__(self, item: ChecklistItemCfg, page: CleaningPage) -> None:
        super().__init__()
        self.item = item
        self.page = page
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 4, 0, 4)
        self._value: Any = None
        row = QHBoxLayout()

        if item.type == "checkbox":
            self.check = QCheckBox(item.label)
            self.check.toggled.connect(lambda _: page.re_evaluate())
            row.addWidget(self.check)
        elif item.type == "yes_no":
            row.addWidget(QLabel(item.label))
            self.group = QButtonGroup(self)
            self.yes = QRadioButton("Yes")
            self.no = QRadioButton("No")
            self.group.addButton(self.yes)
            self.group.addButton(self.no)
            self.yes.toggled.connect(lambda _: page.re_evaluate())
            self.no.toggled.connect(lambda _: page.re_evaluate())
            row.addWidget(self.yes)
            row.addWidget(self.no)
        elif item.type == "select":
            row.addWidget(QLabel(item.label))
            self.combo = QComboBox()
            self.combo.addItems([""] + item.options)
            self.combo.currentTextChanged.connect(lambda _: page.re_evaluate())
            row.addWidget(self.combo)
        elif item.type == "number":
            row.addWidget(QLabel(item.label))
            self.spin = QDoubleSpinBox()
            row.addWidget(self.spin)
        elif item.type == "text":
            row.addWidget(QLabel(item.label))
            self.edit = QLineEdit()
            row.addWidget(self.edit)
        elif item.type == "solvent_clean":
            cfg = page.state.cfg
            self.check = QCheckBox(f"{item.label} ({cfg.solvent.approved_solvent})")
            self.check.toggled.connect(lambda _: page.re_evaluate())
            row.addWidget(self.check)
            self.objective = QComboBox()
            self.objective.setEditable(True)
            row.addWidget(QLabel("Objective:"))
            row.addWidget(self.objective)
            self.last_label = QLabel("")
            self.last_label.setObjectName("solventInfo")
            v.addWidget(self.last_label)
        row.addStretch(1)
        v.insertLayout(0, row)
        if item.help:
            help_label = QLabel(item.help)
            help_label.setWordWrap(True)
            help_label.setObjectName("itemHelp")
            v.addWidget(help_label)

    # -- value access ---------------------------------------------------------------

    def value(self) -> Any:
        t = self.item.type
        if t in ("checkbox",):
            return self.check.isChecked()
        if t == "yes_no":
            if self.yes.isChecked():
                return True
            if self.no.isChecked():
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
            (self.yes if value else self.no).setChecked(True)
        elif t == "solvent_clean" and isinstance(value, dict):
            self.check.setChecked(bool(value.get("done")))


class CleaningPage(WizardPage):
    title = "Cleaning & shutdown checklist"
    short = "Cleaning"

    def build(self) -> None:
        self.items = engine.load_items(self.state.cfg)
        self.widgets: dict[str, _ItemWidget] = {}
        container = QWidget()
        self.items_layout = QVBoxLayout(container)
        for item in self.items:
            w = _ItemWidget(item, self)
            self.widgets[item.key] = w
            self.items_layout.addWidget(w)
        self.layout_.addWidget(container)
        self.layout_.addStretch(1)

    def refresh(self) -> None:
        pre = engine.prefill(self.state.conn, self.state.session_id, self.state.cfg, self.items)
        for key, value in pre.items():
            self.widgets[key].set_value(value)
        self._refresh_solvent_info()
        self.re_evaluate()

    def _refresh_solvent_info(self) -> None:
        for w in self.widgets.values():
            if w.item.type != "solvent_clean":
                continue
            oils = repo.session_oil_objectives(self.state.conn, self.state.session_id)
            w.objective.clear()
            w.objective.addItems(oils or [self.state.cfg.dust.objective])
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
