"""Dust-reference page: confirm the session's blank-FOV image, or log the skip."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel

from ...db import repo
from ...dustref import record_skip, register_session_dust_refs
from ..ui.widgets import SectionCard
from .base import WizardPage


class DustPage(WizardPage):
    title = "Dust reference"
    short = "Dust ref"

    def build(self) -> None:
        cfg = self.state.cfg

        self.have_card = SectionCard("Recorded — thanks!")
        row = QHBoxLayout()
        self.thumb = QLabel()
        row.addWidget(self.thumb)
        self.have_detail = QLabel("")
        self.have_detail.setObjectName("muted")
        row.addWidget(self.have_detail, stretch=1)
        self.have_card.body.addLayout(row)
        self.layout_.addWidget(self.have_card)

        self.miss_card = SectionCard(
            "None detected this session",
            "A 20-second blank shot lets the lab spot new dust and damage early.",
        )
        for step in (
            f"1   Open the saved preset  ·  {cfg.dust.preset_hint}",
            f"2   {cfg.dust.objective} {cfg.dust.modality}, no sample in the light path",
            f"3   Save with a name starting  ·  {cfg.dust.filename_prefix}_",
        ):
            step_label = QLabel(step)
            step_label.setObjectName("cardTitle")
            self.miss_card.body.addWidget(step_label)
        self.layout_.addWidget(self.miss_card)

        self.ack = QCheckBox("I didn't take one this time — noted")
        self.layout_.addWidget(self.ack)
        self.layout_.addStretch(1)

    def refresh(self) -> None:
        register_session_dust_refs(self.state.conn, self.state.session_id)
        self._ref = repo.session_dust_ref(self.state.conn, self.state.session_id)
        if self._ref:
            self.have_card.show()
            self.miss_card.hide()
            self.ack.hide()
            self.have_detail.setText(
                f"Objective: {self._ref['objective_name'] or 'unknown'}"
            )
            if self._ref["thumbnail_path"]:
                pm = QPixmap(self._ref["thumbnail_path"])
                if not pm.isNull():
                    self.thumb.setPixmap(pm.scaledToHeight(140, Qt.SmoothTransformation))
        else:
            self.have_card.hide()
            self.miss_card.show()
            self.ack.show()

    def validate(self) -> str | None:
        needs_ack = self._ref is None and self.state.cfg.dust.required in ("required", "prompt")
        if needs_ack and not self.ack.isChecked():
            return "Tick the acknowledgement so the skip is logged."
        return None

    def save(self) -> None:
        if self._ref is None:
            record_skip(self.state.conn, self.state.session_id)

    def auto_fill(self) -> None:
        self.ack.setChecked(True)
