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
    apply_theme(app)

    state = WizardState(ctx=ctx, reason=reason, session_id=session_id)
    try:
        window = WizardWindow(state)
        if auto_accept:
            window.run_auto()
            return state.exit_code
        mode = ctx.config.ui.effective_mode()
        backdrops = []
        if mode == "fullscreen":
            window.setWindowFlags(
                window.windowFlags() | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
            )
            window.showFullScreen()
        elif mode == "dimmed":
            backdrops = _show_backdrops(app)
            window.setWindowFlags(
                window.windowFlags() | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
            )
            window.setObjectName("wizardSurface")
            window.setAttribute(Qt.WA_StyledBackground)
            _show_centered(window)
        else:
            window.resize(1100, 720)
            window.show()
        app.exec()
        for b in backdrops:
            b.close()
        return state.exit_code
    except Exception:
        log.error("Wizard crashed (reason=%s session=%s)", reason, session_id, exc_info=True)
        return EXIT_ERROR


def _show_backdrops(app) -> list:
    """One inert dimming layer per screen, shown beneath the wizard window."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QWidget

    backdrops = []
    for screen in QGuiApplication.screens():
        shade = QWidget()
        shade.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        # windowOpacity on an opaque widget dims reliably on Windows; QSS rgba
        # translucency on a bare top-level widget does not.
        shade.setAttribute(Qt.WA_StyledBackground)
        shade.setStyleSheet("background: #0f172a;")
        shade.setWindowOpacity(0.5)
        shade.setGeometry(screen.geometry())
        shade.show()
        backdrops.append(shade)
    return backdrops


def _show_centered(window) -> None:
    """Size the wizard to ~85% of the screen (capped) and centre it."""
    from PySide6.QtGui import QGuiApplication

    screen = QGuiApplication.primaryScreen()
    geo = screen.availableGeometry() if screen else None
    if geo is None:
        window.resize(1100, 720)
        window.show()
        return
    width = min(int(geo.width() * 0.85), 1320)
    height = min(int(geo.height() * 0.85), 900)
    window.resize(width, height)
    window.move(
        geo.left() + (geo.width() - width) // 2,
        geo.top() + (geo.height() - height) // 2,
    )
    window.show()
