"""Pre-session experiment declaration page.

Optional: declaring what you're about to image lets the tool auto-tag every file as
it lands, pre-create the scratch session folder, and turn the end-of-session wizard
into a quick review.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from ...db import repo
from ...metadata.naming import build_context, sanitize_token
from ...util import now_iso
from .base import WizardPage

log = logging.getLogger(__name__)


class ExperimentPage(WizardPage):
    title = "What are you imaging today?"
    short = "Plan"

    def build(self) -> None:
        hint = QLabel(
            "Optional, but worth 30 seconds: files get tagged automatically as you "
            "save them, and a session folder is created for you to save into."
        )
        hint.setWordWrap(True)
        hint.setObjectName("itemHelp")
        self.layout_.addWidget(hint)

        form = QFormLayout()
        self.experiment = QComboBox()
        self.experiment.setEditable(True)
        self.experiment.addItems([""] + repo.list_experiment_names(self.state.conn))
        self.strain = QLineEdit()
        self.strain.setPlaceholderText("e.g. MSM155")
        self.condition = QLineEdit()
        self.condition.setPlaceholderText("e.g. 37C, +INH 2xMIC")
        self.coverslip = QLineEdit()
        self.coverslip.setPlaceholderText("e.g. 1.5H, agarose pad")
        self.notes = QLineEdit()
        form.addRow("Experiment:", self.experiment)
        form.addRow("Strain(s):", self.strain)
        form.addRow("Condition:", self.condition)
        form.addRow("Coverslip / prep:", self.coverslip)
        form.addRow("Notes:", self.notes)
        self.layout_.addLayout(form)

        row = QHBoxLayout()
        self.same_btn = QPushButton("Same as my last session")
        self.same_btn.clicked.connect(self._prefill_last)
        row.addWidget(self.same_btn)
        row.addStretch(1)
        self.layout_.addLayout(row)

        self.dir_label = QLabel("")
        self.dir_label.setObjectName("itemHelp")
        self.dir_label.setWordWrap(True)
        self.layout_.addWidget(self.dir_label)
        self.layout_.addStretch(1)

    def refresh(self) -> None:
        self.same_btn.setVisible(
            self.state.user_id is not None
            and repo.last_session_plan_for_user(self.state.conn, self.state.user_id) is not None
        )

    def _prefill_last(self) -> None:
        if self.state.user_id is None:
            return
        last = repo.last_session_plan_for_user(self.state.conn, self.state.user_id)
        if not last:
            return
        self.experiment.setCurrentText(last["planned_experiment_name"] or "")
        self.strain.setText(last["planned_strain"] or "")
        self.condition.setText(last["planned_condition"] or "")
        self.coverslip.setText(last["planned_coverslip"] or "")

    def validate(self) -> str | None:
        return None  # declaring is optional; empty = "not sure yet"

    def save(self) -> None:
        conn = self.state.conn
        experiment = self.experiment.currentText().strip()
        strain = self.strain.text().strip() or None
        condition = self.condition.text().strip() or None
        coverslip = self.coverslip.text().strip() or None
        notes = self.notes.text().strip() or None
        if not any((experiment, strain, condition, coverslip, notes)):
            return  # skipped

        experiment_id = None
        if experiment:
            experiment_id = repo.get_or_create_experiment(conn, experiment, self.state.user_id)

        planned_dir = None
        cfg = self.state.cfg
        root = cfg.effective_scratch_root()
        if cfg.declare.create_scratch_dir and root is not None:
            initials = None
            if self.state.user_id:
                user = repo.get_user(conn, self.state.user_id)
                initials = user["initials"] if user else None
            ctx = build_context(
                acquired_at=now_iso(), initials=initials,
                experiment=experiment, strain=None, condition=None,
            )
            name = "_".join(
                t for t in (ctx["date"], ctx["initials"], sanitize_token(experiment)) if t
            )
            target = Path(root) / name
            try:
                target.mkdir(parents=True, exist_ok=True)
                planned_dir = str(target)
                self.dir_label.setText(f"Session folder ready — save your images into:\n{target}")
            except OSError:
                log.warning("Could not create session folder %s", target, exc_info=True)

        repo.set_session_plan(
            conn, self.state.session_id,
            experiment_id=experiment_id, strain=strain, condition=condition,
            coverslip=coverslip, notes=notes, planned_dir=planned_dir,
        )
        repo.audit(
            conn, "experiment_declared",
            session_id=self.state.session_id, experiment=experiment or None,
            planned_dir=planned_dir,
        )

    def auto_fill(self) -> None:
        self.experiment.setCurrentText("e2e-experiment")
        self.strain.setText("TEST1")
        self.condition.setText("ctrl")
