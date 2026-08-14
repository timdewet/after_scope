"""Save-time annotation toast.

A small always-on-top corner notification shown when new files stabilize during a
session. It never steals keyboard focus from ZEN, and auto-dismisses after a timeout
— the session plan's defaults were already applied at ingest, so silently closing
means "accepted". Clicking 'Change…' expands inline fields to override the batch.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..appcontext import AppContext
from ..db import repo

log = logging.getLogger(__name__)


class AnnotateToast(QWidget):
    def __init__(self, ctx: AppContext, session_id: int, file_ids: list[int],
                 timeout_seconds: int) -> None:
        super().__init__()
        self.ctx = ctx
        self.session_id = session_id
        self.file_ids = file_ids
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setObjectName("annotateToast")
        from .ui import tokens
        from .ui.tokens import active

        p = active()
        self.setStyleSheet(
            f"#annotateToast {{ background: {p.surface};"
            f" border: 1px solid {p.border_strong};"
            f" border-radius: {tokens.R_LG}px; }}"
        )

        v = QVBoxLayout(self)
        rows = repo.session_files(ctx.db, session_id)
        rows = [r for r in rows if r["id"] in set(file_ids)]
        for r in rows[:4]:
            line = QHBoxLayout()
            if r["thumbnail_path"]:
                pm = QPixmap(r["thumbnail_path"])
                if not pm.isNull():
                    thumb = QLabel()
                    thumb.setPixmap(pm.scaledToHeight(36, Qt.SmoothTransformation))
                    line.addWidget(thumb)
            name = r["current_path"].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            tags = " / ".join(t for t in (self._exp_name(r), r["strain"], r["condition"]) if t)
            label = QLabel(
                f"<b>{name}</b><br>"
                f"<span style='color:{p.text_muted}'>{tags or 'untagged'}</span>"
            )
            line.addWidget(label, stretch=1)
            v.addLayout(line)
        if len(rows) > 4:
            v.addWidget(QLabel(f"…and {len(rows) - 4} more"))

        buttons = QHBoxLayout()
        self.change_btn = QPushButton("Change…")
        self.change_btn.clicked.connect(self._expand)
        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self.close)
        buttons.addStretch(1)
        buttons.addWidget(self.change_btn)
        buttons.addWidget(self.ok_btn)
        v.addLayout(buttons)

        # collapsed edit form
        self.form_box = QWidget()
        form = QFormLayout(self.form_box)
        self.experiment = QLineEdit()
        self.strain = QLineEdit()
        self.condition = QLineEdit()
        self.coverslip = QLineEdit()
        self.notes = QLineEdit()
        form.addRow("Experiment:", self.experiment)
        form.addRow("Strain:", self.strain)
        form.addRow("Condition:", self.condition)
        form.addRow("Coverslip:", self.coverslip)
        form.addRow("Notes:", self.notes)
        self.apply_btn = QPushButton("Apply to these files")
        self.apply_btn.clicked.connect(self._apply)
        form.addRow(self.apply_btn)
        self.form_box.hide()
        v.addWidget(self.form_box)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.close)
        self.timer.start(max(3, timeout_seconds) * 1000)

    def _exp_name(self, row) -> str | None:
        if not row["experiment_id"]:
            return None
        r = self.ctx.db.execute(
            "SELECT name FROM experiments WHERE id=?", (row["experiment_id"],)
        ).fetchone()
        return r["name"] if r else None

    def _expand(self) -> None:
        self.timer.stop()  # user is engaging; don't vanish mid-edit
        self.form_box.show()
        self.change_btn.hide()
        self.adjustSize()
        self._position()

    def _apply(self) -> None:
        session = repo.get_session(self.ctx.db, self.session_id)
        user_id = session["user_id"] if session else None
        experiment_id = None
        if self.experiment.text().strip():
            experiment_id = repo.get_or_create_experiment(
                self.ctx.db, self.experiment.text().strip(), user_id
            )
        for fid in self.file_ids:
            repo.set_file_user_meta(
                self.ctx.db, fid,
                experiment_id=experiment_id,
                strain=self.strain.text().strip() or None,
                condition=self.condition.text().strip() or None,
                coverslip=self.coverslip.text().strip() or None,
                notes=self.notes.text().strip() or None,
            )
        self.close()

    def _position(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.adjustSize()
        self.move(geo.right() - self.width() - 24, geo.bottom() - self.height() - 24)

    def show_in_corner(self) -> None:
        self.show()
        self._position()


def run_toast(ctx: AppContext, session_id: int, file_ids: list[int]) -> int:
    import sys

    from .ui.theme import apply_theme

    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_theme(app, mode=ctx.config.ui.theme)
    toast = AnnotateToast(ctx, session_id, file_ids, ctx.config.annotate.timeout_seconds)
    toast.destroyed.connect(app.quit)
    toast.show_in_corner()
    # closing the toast (button, timer) quits the loop
    toast.setAttribute(Qt.WA_DeleteOnClose)
    app.exec()
    return 0
