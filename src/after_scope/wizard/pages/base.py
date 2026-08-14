"""Base class for wizard pages."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..state import WizardState


class WizardPage(QWidget):
    title = ""

    def __init__(self, state: WizardState) -> None:
        super().__init__()
        self.state = state
        self.controller = None  # set by the controller when added
        self._built = False
        self.layout_ = QVBoxLayout(self)
        self.heading = QLabel()
        self.heading.setObjectName("pageTitle")
        self.layout_.addWidget(self.heading)

    def on_enter(self) -> None:
        if not self._built:
            self.build()
            self._built = True
        self.heading.setText(self.title)
        self.refresh()

    def build(self) -> None:  # create widgets (once)
        pass

    def refresh(self) -> None:  # update from current state (each entry)
        pass

    def validate(self) -> str | None:  # None = OK, else error message
        return None

    def save(self) -> None:  # persist page results (called on Next)
        pass

    def auto_fill(self) -> None:  # used by --auto-accept (tests / e2e)
        pass
