"""Dust-reference page: confirm the session's blank-FOV image, or log the skip."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCheckBox, QLabel

from ...db import repo
from ...dustref import record_skip, register_session_dust_refs
from .base import WizardPage


class DustPage(WizardPage):
    title = "Dust reference"
    short = "Dust ref"

    def build(self) -> None:
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.layout_.addWidget(self.body)
        self.thumb = QLabel()
        self.layout_.addWidget(self.thumb)
        self.ack = QCheckBox("I didn't take one this time — noted")
        self.layout_.addWidget(self.ack)
        self.layout_.addStretch(1)

    def refresh(self) -> None:
        register_session_dust_refs(self.state.conn, self.state.session_id)
        self._ref = repo.session_dust_ref(self.state.conn, self.state.session_id)
        cfg = self.state.cfg
        if self._ref:
            self.body.setText(
                f"Dust reference recorded for this session ({self._ref['objective_name'] or 'objective unknown'}). Thanks!"
            )
            self.ack.hide()
            if self._ref["thumbnail_path"]:
                pm = QPixmap(self._ref["thumbnail_path"])
                if not pm.isNull():
                    self.thumb.setPixmap(pm.scaledToHeight(180, Qt.SmoothTransformation))
        else:
            self.body.setText(
                "No dust reference detected this session.\n\n"
                f"Next time, before closing ZEN: run the saved preset "
                f"'{cfg.dust.preset_hint}' ({cfg.dust.objective}, {cfg.dust.modality}, no sample) "
                f"and save it with a name starting '{cfg.dust.filename_prefix}_'. "
                "It takes ~20 seconds and lets the lab track new dust and damage."
            )
            self.ack.show()

    def validate(self) -> str | None:
        if self._ref is None and self.state.cfg.dust.required == "required" and not self.ack.isChecked():
            return "Acknowledge the missing dust reference."
        if self._ref is None and self.state.cfg.dust.required == "prompt" and not self.ack.isChecked():
            return "Tick the acknowledgement so the skip is logged."
        return None

    def save(self) -> None:
        if self._ref is None:
            record_skip(self.state.conn, self.state.session_id)

    def auto_fill(self) -> None:
        self.ack.setChecked(True)
