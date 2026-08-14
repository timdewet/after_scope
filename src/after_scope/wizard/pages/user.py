"""User identification pages: roster picker + 'I'm new', and the whoami re-confirm."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from ...db import repo
from ..state import EXIT_COMPLETE, EXIT_HANDOVER
from .base import WizardPage


class UserPage(WizardPage):
    title = "Who's using the microscope?"
    short = "Who"

    def build(self) -> None:
        self.selected_uid: int | None = None
        self.method = "roster"
        self.selected_label = QLabel("")
        self.selected_label.setObjectName("selectedUser")
        self.roster_box = QWidget()
        self.roster_grid = QGridLayout(self.roster_box)
        self.layout_.addWidget(self.roster_box)
        self.layout_.addWidget(self.selected_label)

        new_box = QGroupBox("I'm new — add me to the roster")
        form = QHBoxLayout(new_box)
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText("Full name")
        self.new_initials = QLineEdit()
        self.new_initials.setPlaceholderText("Initials (e.g. TdW)")
        self.new_initials.setMaximumWidth(160)
        self.new_email = QLineEdit()
        self.new_email.setPlaceholderText("Email (optional)")
        add_btn = QPushButton("Add me")
        add_btn.clicked.connect(self._add_new)
        for w in (self.new_name, self.new_initials, self.new_email, add_btn):
            form.addWidget(w)
        self.layout_.addWidget(new_box)
        self.layout_.addStretch(1)

    def refresh(self) -> None:
        if self.state.is_end_of_session:
            self.heading.setText("Who was using the microscope?")
        # rebuild roster buttons (recent users first)
        while self.roster_grid.count():
            item = self.roster_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        users = repo.recent_users(self.state.conn, limit=6)
        seen = {u["id"] for u in users}
        users += [u for u in repo.list_users(self.state.conn) if u["id"] not in seen]
        for i, user in enumerate(users):
            btn = QPushButton(f"{user['full_name']}  ({user['initials']})")
            btn.setObjectName("rosterButton")
            btn.clicked.connect(lambda _=False, uid=user["id"], name=user["full_name"]:
                                self._pick(uid, name))
            self.roster_grid.addWidget(btn, i // 3, i % 3)
        # session may already carry a user (pre-use identified them)
        row = repo.get_session(self.state.conn, self.state.session_id)
        if row and row["user_id"] and self.selected_uid is None:
            user = repo.get_user(self.state.conn, row["user_id"])
            if user:
                self._pick(user["id"], user["full_name"], method=row["identify_method"] or "roster")
        elif self.state.is_end_of_session and self.selected_uid is None and users:
            # end-of-session with no identity on record: pre-select the most
            # recent user so confirming is one tap (still freely changeable)
            self._pick(users[0]["id"], users[0]["full_name"])

    def _pick(self, uid: int, name: str, method: str = "roster") -> None:
        self.selected_uid = uid
        self.method = method
        self.selected_label.setText(f"Selected: {name}")

    def _add_new(self) -> None:
        name = self.new_name.text().strip()
        initials = self.new_initials.text().strip()
        if not name or not initials:
            self.selected_label.setText("Enter a name and initials first.")
            return
        try:
            uid = repo.add_user(self.state.conn, name, initials, self.new_email.text().strip() or None)
        except Exception:
            self.selected_label.setText(f"Initials '{initials}' already exist — pick your roster button.")
            self.refresh()
            return
        self._pick(uid, name, method="new")
        self.refresh()

    def validate(self) -> str | None:
        if self.selected_uid is None:
            return "Pick who you are (or add yourself to the roster)."
        return None

    def save(self) -> None:
        repo.set_session_user(self.state.conn, self.state.session_id, self.selected_uid, self.method)
        self.state.user_id = self.selected_uid

    def auto_fill(self) -> None:
        initials = os.environ.get("AFTER_SCOPE_AUTO_USER")
        users = repo.list_users(self.state.conn)
        target = None
        if initials:
            target = next((u for u in users if u["initials"] == initials), None)
        if target is None and users:
            target = users[0]
        if target:
            self._pick(target["id"], target["full_name"])


class WhoamiPage(WizardPage):
    title = "Who's at the microscope?"
    short = "Who"

    def build(self) -> None:
        self.info = QLabel()
        self.layout_.addWidget(self.info)
        row = QHBoxLayout()
        self.still_btn = QPushButton()
        self.still_btn.setObjectName("bigYes")
        self.still_btn.clicked.connect(self._still_me)
        self.other_btn = QPushButton("Someone else — I'm taking over")
        self.other_btn.clicked.connect(self._someone_else)
        row.addWidget(self.still_btn)
        row.addWidget(self.other_btn)
        self.layout_.addLayout(row)
        self.picker_box = QGroupBox("Who are you?")
        self.picker_grid = QGridLayout(self.picker_box)
        self.picker_box.hide()
        self.layout_.addWidget(self.picker_box)
        self.layout_.addStretch(1)

    def refresh(self) -> None:
        row = repo.get_session(self.state.conn, self.state.session_id)
        name = "the previous user"
        if row and row["user_id"]:
            user = repo.get_user(self.state.conn, row["user_id"])
            name = user["full_name"] if user else name
        self._current_name = name
        self.info.setText(
            f"ZEN has been idle for a while. The session belongs to {name}."
        )
        self.still_btn.setText(f"Still {name} — continue")

    def _still_me(self) -> None:
        self.controller.finish(EXIT_COMPLETE)

    def _someone_else(self) -> None:
        while self.picker_grid.count():
            item = self.picker_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, user in enumerate(repo.list_users(self.state.conn)):
            btn = QPushButton(f"{user['full_name']} ({user['initials']})")
            btn.clicked.connect(lambda _=False, uid=user["id"]: self._take_over(uid))
            self.picker_grid.addWidget(btn, i // 3, i % 3)
        self.picker_box.show()

    def _take_over(self, uid: int) -> None:
        sm = self.state.sm
        new_sid = sm.handover(self.state.session_id)
        repo.set_session_user(self.state.conn, new_sid, uid, "roster")
        self.state.session_id = new_sid
        self.state.user_id = uid
        self.state.handover_happened = True
        self.state.exit_code = EXIT_HANDOVER
        # continue into the pre-use pages (arrival check, open issues) for the new user
        self.controller.extend_with_preuse()
        self.controller.advance()

    def auto_fill(self) -> None:
        # auto mode answers "still me" — handover paths are tested via effects
        pass

    def validate(self) -> str | None:
        return None
