"""Drop shadows — QSS can't do them, so attach a QGraphicsDropShadowEffect."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

from .tokens import active

_LEVELS = {1: (14, 2), 2: (22, 6)}  # blur radius, y-offset


def apply_shadow(widget: QWidget, level: int = 1) -> None:
    blur, dy = _LEVELS.get(level, _LEVELS[1])
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, dy)
    dark = active().name == "dark"
    effect.setColor(QColor(0, 0, 0, 140) if dark else QColor(15, 23, 42, 30))
    widget.setGraphicsEffect(effect)
