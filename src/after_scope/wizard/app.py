"""Wizard process entry point."""

from __future__ import annotations

import logging
import sys
from importlib import resources

from ..appcontext import AppContext
from .state import EXIT_ERROR, WizardState

log = logging.getLogger(__name__)


def run_wizard(
    ctx: AppContext, session_id: int, reason: str, auto_accept: bool = False
) -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from .controller import WizardWindow

    app = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        app.setStyleSheet(
            (resources.files("after_scope.wizard") / "style.qss").read_text(encoding="utf-8")
        )
    except OSError:
        pass

    state = WizardState(ctx=ctx, reason=reason, session_id=session_id)
    try:
        window = WizardWindow(state)
        if auto_accept:
            window.run_auto()
            return state.exit_code
        if ctx.config.ui.kiosk:
            window.setWindowFlags(
                window.windowFlags() | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
            )
            window.showFullScreen()
        else:
            window.resize(1100, 720)
            window.show()
        app.exec()
        return state.exit_code
    except Exception:
        log.error("Wizard crashed (reason=%s session=%s)", reason, session_id, exc_info=True)
        return EXIT_ERROR
