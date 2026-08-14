"""Wizard window: page flow, skip protocol, exit codes, auto-accept driver."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..db import repo
from .state import EXIT_SKIPPED, PREUSE_REASONS, WizardState

log = logging.getLogger(__name__)


def build_pages(state: WizardState) -> list:
    from .pages.cleaning import CleaningPage
    from .pages.declare import ExperimentPage
    from .pages.dust import DustPage
    from .pages.files import FilesPage
    from .pages.incidents import IncidentPage
    from .pages.naming import NamingPage
    from .pages.preuse import ArrivalPage, IssuesPage, NagOfferPage
    from .pages.summary import SummaryPage
    from .pages.user import UserPage, WhoamiPage

    if state.reason == "whoami":
        return [WhoamiPage(state)]
    if state.reason == "declare":
        return [ExperimentPage(state)]
    if state.reason in PREUSE_REASONS:
        from .pages.preuse import SavingPage

        pages = [UserPage(state)]
        if state.cfg.declare.enabled:
            pages.append(ExperimentPage(state))
        pages += [ArrivalPage(state), IssuesPage(state)]
        if state.reason == "start" and state.sm.pending_nag() is not None:
            pages.append(NagOfferPage(state))
        pages.append(SavingPage(state))
        return pages
    # end-of-session (close | crash | nag)
    pages = [
        UserPage(state),
        FilesPage(state),
        NamingPage(state),
        CleaningPage(state),
    ]
    if state.cfg.dust.required != "off":
        pages.append(DustPage(state))
    pages += [IncidentPage(state), SummaryPage(state)]
    return pages


def end_pages_for_retro(retro_state: WizardState) -> list:
    from .pages.cleaning import CleaningPage
    from .pages.dust import DustPage
    from .pages.files import FilesPage
    from .pages.incidents import IncidentPage
    from .pages.naming import NamingPage
    from .pages.summary import SummaryPage
    from .pages.user import UserPage

    pages = [UserPage(retro_state), FilesPage(retro_state), NamingPage(retro_state),
             CleaningPage(retro_state)]
    if retro_state.cfg.dust.required != "off":
        pages.append(DustPage(retro_state))
    pages += [IncidentPage(retro_state), SummaryPage(retro_state)]
    return pages


QUICK_SKIP_PURPOSES = ["Image viewing", "Analysis only", "Quick look"]


class SkipDialog(QDialog):
    def __init__(self, require_reason: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Skip checklist")
        self.quick_purpose: str | None = None
        v = QVBoxLayout(self)
        v.setSpacing(10)
        v.addWidget(QLabel(
            "Skipping is allowed but logged, and the checklist will come back at the "
            "next session start."
        ))
        quick_label = QLabel("NOT AN EXPERIMENT?  One tap skips with the reason logged:")
        quick_label.setObjectName("fieldLabel")
        v.addWidget(quick_label)
        chips = QHBoxLayout()
        for purpose in QUICK_SKIP_PURPOSES:
            btn = QPushButton(purpose)
            btn.setObjectName("chip")
            btn.clicked.connect(lambda _=False, p=purpose: self._quick(p))
            chips.addWidget(btn)
        chips.addStretch(1)
        v.addLayout(chips)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Other reason (required)" if require_reason
                                       else "Other reason (optional)")
        v.addWidget(self.reason)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)
        self._require = require_reason

    def _quick(self, purpose: str) -> None:
        self.quick_purpose = purpose
        self.reason.setText(purpose)
        self.accept()

    def _try_accept(self) -> None:
        if self._require and not self.reason.text().strip():
            self.reason.setFocus()
            return
        self.accept()


class WizardWindow(QWidget):
    def __init__(self, state: WizardState) -> None:
        super().__init__()
        self.state = state
        self.setWindowTitle("AfterScope")
        self._finishing = False
        self.pages = build_pages(state)
        for p in self.pages:
            p.controller = self

        from .ui import tokens
        from .ui.stepper import Stepper

        v = QVBoxLayout(self)
        v.setContentsMargins(tokens.S6, tokens.S5, tokens.S6, tokens.S4)
        v.setSpacing(tokens.S3)
        self.stepper = Stepper()
        v.addWidget(self.stepper)
        self.stack = QStackedWidget()
        for p in self.pages:
            self.stack.addWidget(p)
        v.addWidget(self.stack, stretch=1)

        footer = QHBoxLayout()
        self.back_btn = QPushButton("← Back")
        self.back_btn.clicked.connect(self.back)
        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.progress = QLabel("")
        self.progress.setObjectName("caption")
        self.next_btn = QPushButton("Next →")
        self.next_btn.setObjectName("nextButton")
        self.next_btn.clicked.connect(self.next_clicked)
        footer.addWidget(self.back_btn)
        footer.addWidget(self.error_label, stretch=1)
        footer.addWidget(self.progress)
        footer.addWidget(self.next_btn)
        v.addLayout(footer)

        if state.cfg.enforcement.allow_skip:
            self.skip_link = QPushButton("Skip checklist (logged)")
            self.skip_link.setObjectName("skipLink")
            self.skip_link.setFlat(True)
            self.skip_link.clicked.connect(self.skip_flow)
            v.addWidget(self.skip_link, alignment=Qt.AlignRight)

        self.index = 0
        self._enter_current()

    # -- flow -----------------------------------------------------------------------

    def _enter_current(self) -> None:
        page = self.pages[self.index]
        self.stack.setCurrentWidget(page)
        page.on_enter()
        self.error_label.setText("")
        self.back_btn.setVisible(self.index > 0)
        self.progress.setText(f"Step {self.index + 1} of {len(self.pages)}")
        self.next_btn.setText("Done ✓" if self.index == len(self.pages) - 1 else "Next →")
        self._sync_stepper()

    def _sync_stepper(self) -> None:
        titles = [p.short or p.title for p in self.pages]
        if titles != getattr(self, "_stepper_titles", None):
            self._stepper_titles = titles
            self.stepper.set_steps(titles)
        self.stepper.set_current(self.index)

    def next_clicked(self) -> None:
        page = self.pages[self.index]
        err = page.validate()
        if err:
            self.error_label.setText(err)
            return
        try:
            page.save()
        except Exception:
            log.error("Page save failed on %s", type(page).__name__, exc_info=True)
            self.error_label.setText("Something went wrong saving this page — see logs.")
            return
        self.advance()

    def advance(self) -> None:
        if self.index >= len(self.pages) - 1:
            self.finish()
            return
        self.index += 1
        self._enter_current()

    def back(self) -> None:
        if self.index > 0:
            self.index -= 1
            self._enter_current()

    def extend_with_preuse(self) -> None:
        from .pages.declare import ExperimentPage
        from .pages.preuse import ArrivalPage, IssuesPage

        pages = []
        if self.state.cfg.declare.enabled:
            pages.append(ExperimentPage(self.state))
        pages += [ArrivalPage(self.state), IssuesPage(self.state)]
        for page in pages:
            page.controller = self
            self.pages.append(page)
            self.stack.addWidget(page)

    def extend_with_retro(self, retro_session_id: int) -> None:
        retro_state = WizardState(
            ctx=self.state.ctx, reason="nag", session_id=retro_session_id
        )
        for page in end_pages_for_retro(retro_state):
            page.controller = self
            self.pages.append(page)
            self.stack.addWidget(page)

    # -- outcomes -------------------------------------------------------------------

    def finish(self, code: int | None = None) -> None:
        if code is not None:
            self.state.exit_code = code
        self._finishing = True
        self.close()
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()

    def skip_flow(self) -> None:
        dlg = SkipDialog(self.state.cfg.enforcement.skip_requires_reason, self)
        if dlg.exec() != QDialog.Accepted:
            return
        reason = dlg.reason.text().strip()
        if dlg.quick_purpose:
            # a quick reason doubles as the session's declared purpose
            repo.set_session_purpose(
                self.state.conn, self.state.session_id, dlg.quick_purpose
            )
        if self.state.is_end_of_session:
            self.state.sm.checklist_skipped(self.state.session_id, reason)
        else:
            repo.audit(
                self.state.conn, "preuse_skipped",
                session_id=self.state.session_id, reason=reason,
            )
        self.finish(EXIT_SKIPPED)

    def closeEvent(self, event) -> None:
        # Programmatic closes (finish(), test teardown, app shutdown) pass through;
        # only a visible window's user-initiated close routes into the skip protocol.
        if self._finishing or not self.isVisible():
            event.accept()
            return
        # Alt+F4 / window close routes through the same logged-skip protocol
        if self.state.cfg.enforcement.allow_skip:
            event.ignore()
            self.skip_flow()
        else:
            event.ignore()

    # -- auto-accept (tests / e2e) --------------------------------------------------

    def run_auto(self) -> None:
        guard = 0
        while guard < 50:
            guard += 1
            page = self.pages[self.index]
            page.on_enter()
            page.auto_fill()
            err = page.validate()
            if err:
                raise RuntimeError(f"auto-accept blocked on {type(page).__name__}: {err}")
            page.save()
            if self.index >= len(self.pages) - 1:
                self._finishing = True
                return
            self.index += 1
