"""Pre-session experiment declaration page.

Optional: declaring what you're about to image lets the tool auto-tag every file as
it lands, pre-create the scratch session folder, and turn the end-of-session wizard
into a quick review.

Structured after common bioimaging metadata practice (REMBI): the *biological
sample* (strain, condition/treatment, preparation) is captured separately from
the *imaging plan* (modality, objective, timing). Chips are quick-input that
compose into plain-text canonical fields — free typing always works.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from ...db import repo
from ...metadata.naming import build_context, sanitize_token
from ...util import now_iso
from ..ui.widgets import ChipGroup, SectionCard
from .base import WizardPage

log = logging.getLogger(__name__)

CONDITION_CHIPS = ["RT", "30C", "37C", "aerobic", "hypoxia"]
PREP_CHIPS = ["agarose pad", "1.5H coverslip", "glass-bottom dish", "fixed slide"]
MODALITY_CHIPS = ["brightfield", "phase", "fluorescence", "z-stack", "timelapse", "tiling"]
OBJECTIVE_CHIPS = ["10x", "40x", "63x", "100x oil"]


def _completer(values: list[str]) -> QCompleter:
    completer = QCompleter(values)
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    return completer


class ExperimentPage(WizardPage):
    title = "What are you imaging today?"
    short = "Plan"

    QUICK_PURPOSES = ["Image viewing", "Analysis only", "Quick look"]

    def build(self) -> None:
        hint = QLabel(
            "Optional — 30 seconds here tags every file automatically as you save it."
        )
        hint.setObjectName("caption")
        self.layout_.addWidget(hint)

        # one-tap escape for non-experiment sessions: records the purpose and
        # skips the whole form
        quick_row = QHBoxLayout()
        quick_label = QLabel("NOT AN EXPERIMENT?")
        quick_label.setObjectName("fieldLabel")
        quick_row.addWidget(quick_label)
        for purpose in self.QUICK_PURPOSES:
            btn = QPushButton(purpose)
            btn.setObjectName("chip")
            btn.clicked.connect(lambda _=False, p=purpose: self._quick_purpose(p))
            quick_row.addWidget(btn)
        quick_row.addStretch(1)
        self.layout_.addLayout(quick_row)

        conn = self.state.conn
        columns = QHBoxLayout()
        columns.setSpacing(16)

        # -- biological sample ------------------------------------------------
        bio = SectionCard(
            "Biological sample", "What is on the stage — strain, treatment, prep."
        )
        self.experiment = QComboBox()
        self.experiment.setEditable(True)
        self.experiment.addItems([""] + repo.list_experiment_names(conn))
        bio.add_field("EXPERIMENT", self.experiment)

        self.strain = QLineEdit()
        self.strain.setPlaceholderText("e.g. MSM155")
        self.strain.setCompleter(_completer(repo.recent_file_values(conn, "strain")))
        recent_strains = repo.recent_file_values(conn, "strain", limit=4)
        widgets = [self.strain]
        if recent_strains:
            widgets.append(ChipGroup(recent_strains, target=self.strain))
        bio.add_field("STRAIN(S)", *widgets)

        self.condition = QLineEdit()
        self.condition.setPlaceholderText("temperature, drug + concentration…")
        self.condition.setCompleter(_completer(repo.recent_file_values(conn, "condition")))
        recent_conditions = [
            v for v in repo.recent_file_values(conn, "condition", limit=3)
            if v not in CONDITION_CHIPS
        ]
        bio.add_field(
            "CONDITION / TREATMENT",
            self.condition,
            ChipGroup(CONDITION_CHIPS + recent_conditions, target=self.condition),
        )

        self.coverslip = QLineEdit()
        self.coverslip.setPlaceholderText("sample preparation…")
        bio.add_field(
            "PREPARATION",
            self.coverslip,
            ChipGroup(PREP_CHIPS, target=self.coverslip, exclusive=True),
        )
        bio.body.addStretch(1)

        # -- imaging plan ------------------------------------------------------
        imaging = SectionCard(
            "Imaging plan",
            "How you'll acquire — actual optics are read from each CZI at save.",
        )
        self.imaging = QLineEdit()
        self.imaging.setPlaceholderText("modality, objective, interval…")
        imaging.add_field(
            "MODALITY", self.imaging, ChipGroup(MODALITY_CHIPS, target=self.imaging)
        )
        imaging.add_field(
            "OBJECTIVE", ChipGroup(OBJECTIVE_CHIPS, target=self.imaging, exclusive=True)
        )
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("anything else worth remembering")
        imaging.add_field("NOTES", self.notes)
        imaging.body.addStretch(1)

        columns.addWidget(bio, stretch=1)
        columns.addWidget(imaging, stretch=1)
        self.layout_.addLayout(columns)

        row = QHBoxLayout()
        self.same_btn = QPushButton("↺  Same as my last session")
        self.same_btn.clicked.connect(self._prefill_last)
        row.addWidget(self.same_btn)
        row.addStretch(1)
        self.layout_.addLayout(row)

        self.dir_label = QLabel("")
        self.dir_label.setObjectName("caption")
        self.dir_label.setWordWrap(True)
        self.layout_.addWidget(self.dir_label)

        saving = SectionCard("How saving works")
        watch = self.state.cfg.watch_dirs
        working_dir = str(watch[0].path) if watch else "the working directory"
        for line in (
            f"1   Save your images into  {working_dir}  during the session"
            "  (a session folder is created there when you declare above)",
            "2   When ZEN closes, AfterScope renames them to the lab convention"
            " and files them into the shared Dropbox tree",
            "3   Saving into your own Dropbox folder is possible, but those files"
            " are not catalogued",
        ):
            row = QLabel(line)
            row.setObjectName("cardTitle")
            row.setWordWrap(True)
            saving.body.addWidget(row)
        self.layout_.addWidget(saving)
        self.layout_.addStretch(1)

    def _quick_purpose(self, purpose: str) -> None:
        repo.set_session_purpose(self.state.conn, self.state.session_id, purpose)
        repo.audit(
            self.state.conn, "session_purpose",
            session_id=self.state.session_id, purpose=purpose,
        )
        self.controller.advance()  # skips save(): the form is deliberately empty

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
        try:
            self.imaging.setText(last["planned_imaging"] or "")
        except (KeyError, IndexError):
            pass  # row predates the planned_imaging column

    def validate(self) -> str | None:
        return None  # declaring is optional; empty = "not sure yet"

    def save(self) -> None:
        conn = self.state.conn
        experiment = self.experiment.currentText().strip()
        strain = self.strain.text().strip() or None
        condition = self.condition.text().strip() or None
        coverslip = self.coverslip.text().strip() or None
        imaging = self.imaging.text().strip() or None
        notes = self.notes.text().strip() or None
        if not any((experiment, strain, condition, coverslip, imaging, notes)):
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
            imaging=imaging,
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
