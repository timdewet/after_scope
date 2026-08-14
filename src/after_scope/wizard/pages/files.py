"""Files & metadata page: table of session files + batch-apply bar."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
)

from ...db import repo
from ..models import SessionFilesModel
from .base import WizardPage


class FilesPage(WizardPage):
    title = "Your images from this session"
    short = "Images"

    def build(self) -> None:
        self.model = SessionFilesModel(self.state.conn, self.state.session_id)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.resizeColumnsToContents()
        self.layout_.addWidget(self.table, stretch=1)

        box = QGroupBox("Apply to selected rows (or all, when nothing is selected)")
        bar = QHBoxLayout(box)
        self.experiment = QLineEdit()
        self.experiment.setPlaceholderText("Experiment")
        self.experiment.setCompleter(
            QCompleter(repo.list_experiment_names(self.state.conn))
        )
        self.strain = QLineEdit()
        self.strain.setPlaceholderText("Strain(s)")
        self.strain.setCompleter(QCompleter(repo.recent_file_values(self.state.conn, "strain")))
        self.condition = QLineEdit()
        self.condition.setPlaceholderText("Condition / treatment")
        self.condition.setCompleter(
            QCompleter(repo.recent_file_values(self.state.conn, "condition"))
        )
        self.coverslip = QLineEdit()
        self.coverslip.setPlaceholderText("Preparation")
        self.coverslip.setCompleter(
            QCompleter(repo.recent_file_values(self.state.conn, "coverslip"))
        )
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Notes")
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        for w in (self.experiment, self.strain, self.condition, self.coverslip, self.notes, apply_btn):
            bar.addWidget(w)
        self.layout_.addWidget(box)
        self.hint = QLabel(
            "Tip: double-click any cell to edit one file; tick Junk for focus tests "
            "and misfires — junk stays logged but isn't renamed or moved."
        )
        self.hint.setWordWrap(True)
        self.layout_.addWidget(self.hint)

    def refresh(self) -> None:
        self.model.reload()
        self.table.resizeColumnsToContents()
        if not self.model.rows:
            self.hint.setText(
                "No new image files were detected this session. If you saved somewhere "
                "unusual, tell the lab manager so the watched folders can be updated."
            )

    def _apply(self) -> None:
        selected = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        self.model.apply_batch(
            selected,
            experiment=self.experiment.text().strip(),
            strain=self.strain.text().strip(),
            condition=self.condition.text().strip(),
            coverslip=self.coverslip.text().strip(),
            notes=self.notes.text().strip(),
        )

    def save(self) -> None:
        self.model.save_to_db(self.state.user_id)

    def auto_fill(self) -> None:
        self.model.apply_batch([], experiment="e2e-experiment", strain="TEST1", condition="ctrl")
