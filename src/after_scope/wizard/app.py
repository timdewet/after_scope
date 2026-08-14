"""Wizard process entry point."""

from __future__ import annotations

import logging
import sys

from ..appcontext import AppContext
from .state import EXIT_ERROR, WizardState

log = logging.getLogger(__name__)


def run_wizard(
    ctx: AppContext, session_id: int, reason: str, auto_accept: bool = False
) -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from .controller import WizardWindow
    from .ui.theme import apply_theme

    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_theme(app, mode=ctx.config.ui.theme)

    state = WizardState(ctx=ctx, reason=reason, session_id=session_id)
    try:
        window = WizardWindow(state)
        if auto_accept:
            window.run_auto()
            return state.exit_code
        mode = ctx.config.ui.effective_mode()
        host = None
        if mode == "fullscreen":
            window.setWindowFlags(
                window.windowFlags() | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
            )
            window.showFullScreen()
        elif mode == "dimmed":
            host = _DimHost(window)
            host.showFullScreen()
        else:
            window.resize(1100, 720)
            window.show()
        app.exec()
        if host is not None:
            host.close()
        return state.exit_code
    except Exception:
        log.error("Wizard crashed (reason=%s session=%s)", reason, session_id, exc_info=True)
        return EXIT_ERROR


class _DimHost:
    """Single fullscreen translucent window that paints the dim itself and hosts
    the wizard as a centered child — no sibling z-order to get wrong."""

    def __new__(cls, wizard):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QGuiApplication, QPainter
        from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

        class Host(QWidget):
            def __init__(self, wizard_widget) -> None:
                super().__init__()
                self.wizard = wizard_widget
                self.setWindowTitle("AfterScope")
                self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
                self.setAttribute(Qt.WA_TranslucentBackground)

                wizard_widget.setObjectName("wizardSurface")
                wizard_widget.setAttribute(Qt.WA_StyledBackground)
                screen = QGuiApplication.primaryScreen()
                geo = screen.availableGeometry() if screen else None
                if geo is not None:
                    wizard_widget.setFixedSize(
                        min(int(geo.width() * 0.85), 1320),
                        min(int(geo.height() * 0.85), 900),
                    )
                else:
                    wizard_widget.setFixedSize(1100, 720)

                outer = QVBoxLayout(self)
                outer.setContentsMargins(0, 0, 0, 0)
                inner = QHBoxLayout()
                inner.addStretch(1)
                inner.addWidget(wizard_widget)
                inner.addStretch(1)
                outer.addStretch(1)
                outer.addLayout(inner)
                outer.addStretch(1)

            def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
                painter = QPainter(self)
                painter.fillRect(self.rect(), QColor(15, 23, 42, 140))
                painter.end()

            def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
                # Alt+F4 lands on the host; route it through the wizard's own
                # close/skip protocol instead of vanishing silently.
                if self.wizard.isVisible():
                    event.ignore()
                    self.wizard.close()
                else:
                    event.accept()

        return Host(wizard)
