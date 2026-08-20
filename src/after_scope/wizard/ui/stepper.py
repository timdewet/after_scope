"""Horizontal step indicator: numbered badge per page, ✓ once passed.

The wizard can grow pages mid-flow (handover → pre-use pages, retro checklist),
so `set_steps()` rebuilds and `set_current()` just repaints.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from . import tokens as t
from .tokens import active

BADGE = 28


class _StepBadge(QWidget):
    def __init__(self, number: int) -> None:
        super().__init__()
        self.number = number
        self.state = "upcoming"  # upcoming | current | done
        self.setFixedSize(BADGE, BADGE)

    def set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        p = active()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(1, 1, BADGE - 2, BADGE - 2)
        if self.state == "done":
            fill, fg, border = p.success, p.on_primary, p.success
        elif self.state == "current":
            fill, fg, border = p.primary, p.on_primary, p.primary
        else:
            fill, fg, border = p.surface_alt, p.text_muted, p.border_strong
        painter.setPen(QColor(border))
        painter.setBrush(QColor(fill))
        painter.drawEllipse(rect)
        painter.setPen(QColor(fg))
        font = QFont()
        font.setPixelSize(t.FS_BODY)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        text = "✓" if self.state == "done" else str(self.number)
        painter.drawText(rect, Qt.AlignCenter, text)
        painter.end()


class Stepper(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, t.S3)
        self._layout.setSpacing(t.S3)
        self._badges: list[_StepBadge] = []
        self._labels: list[QLabel] = []
        self._current = 0

    def set_steps(self, titles: list[str]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._badges, self._labels = [], []
        for i, title in enumerate(titles):
            badge = _StepBadge(i + 1)
            label = QLabel(title)
            label.setObjectName("muted")
            self._badges.append(badge)
            self._labels.append(label)
            self._layout.addWidget(badge)
            self._layout.addWidget(label)
            if i < len(titles) - 1:
                self._layout.addSpacing(t.S2)
        self._layout.addStretch(1)
        self.set_current(min(self._current, max(len(titles) - 1, 0)))

    def set_current(self, index: int) -> None:
        self._current = index
        p = active()
        for i, (badge, label) in enumerate(zip(self._badges, self._labels, strict=True)):
            if i < index:
                badge.set_state("done")
                label.setStyleSheet(f"color: {p.text_muted};")
            elif i == index:
                badge.set_state("current")
                label.setStyleSheet(
                    f"color: {p.text}; font-weight: {t.FW_SEMIBOLD};"
                )
            else:
                badge.set_state("upcoming")
                label.setStyleSheet(f"color: {p.text_subtle};")
