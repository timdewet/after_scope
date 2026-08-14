"""Pre-use pages: arrival condition, open-issues board, retro-checklist offer."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ...db import repo
from ...util import fmt_dt
from ..ui.widgets import EmptyState, ListCard
from .base import WizardPage

FOUND_DIRTY_CATEGORIES = [
    ("found_dirty_oil", "Oil on the stage or objectives"),
    ("found_sample", "Someone's sample/slide left behind"),
    ("not_parked", "Objective/stage not parked"),
    ("dirty_objective", "Dirty or smeared objective"),
    ("other", "Something else"),
]


class ArrivalPage(WizardPage):
    title = "Was everything OK when you arrived?"
    short = "Arrival"

    def build(self) -> None:
        self.choice: bool | None = None
        row = QHBoxLayout()
        row.setSpacing(16)
        self.ok_btn = QPushButton("All good 👍")
        self.ok_btn.setObjectName("bigYes")
        self.ok_btn.setMinimumHeight(64)
        self.ok_btn.clicked.connect(lambda: self._set_choice(True))
        self.dirty_btn = QPushButton("I found problems…")
        self.dirty_btn.setMinimumHeight(64)
        self.dirty_btn.clicked.connect(lambda: self._set_choice(False))
        row.addWidget(self.ok_btn, stretch=1)
        row.addWidget(self.dirty_btn, stretch=1)
        self.layout_.addLayout(row)

        self.detail_box = QGroupBox("What did you find? (reported to the lab, attributed to the previous session)")
        v = QVBoxLayout(self.detail_box)
        self.category_checks: dict[str, QCheckBox] = {}
        for key, label in FOUND_DIRTY_CATEGORIES:
            cb = QCheckBox(label)
            self.category_checks[key] = cb
            v.addWidget(cb)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Details (optional)")
        v.addWidget(self.note)
        photo_row = QHBoxLayout()
        self.photo_btn = QPushButton("Attach photo…")
        self.photo_btn.clicked.connect(self._pick_photo)
        self.photo_label = QLabel("")
        photo_row.addWidget(self.photo_btn)
        photo_row.addWidget(self.photo_label)
        photo_row.addStretch(1)
        v.addLayout(photo_row)
        self.detail_box.hide()
        self.layout_.addWidget(self.detail_box)
        self.layout_.addStretch(1)
        self.photo_path: str | None = None

    def _set_choice(self, ok: bool) -> None:
        self.choice = ok
        self.detail_box.setVisible(not ok)
        self.ok_btn.setDown(ok)
        self.dirty_btn.setDown(not ok)

    def _pick_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Photo", "", "Images (*.png *.jpg *.jpeg)")
        if path:
            self.photo_path = path
            self.photo_label.setText(path.rsplit("/", 1)[-1])

    def validate(self) -> str | None:
        if self.choice is None:
            return "Tell us whether the scope was OK when you arrived."
        if self.choice is False and not any(cb.isChecked() for cb in self.category_checks.values()):
            return "Tick at least one problem category (or go back to 'All good')."
        return None

    def save(self) -> None:
        conn = self.state.conn
        repo.set_arrival_state(conn, self.state.session_id, bool(self.choice))
        if self.choice:
            return
        prev = repo.previous_session(conn, self.state.session_id)
        photo = self._store_photo() if self.photo_path else None
        for key, cb in self.category_checks.items():
            if not cb.isChecked():
                continue
            repo.add_incident(
                conn,
                session_id=self.state.session_id,
                attributed_session_id=prev["id"] if prev else None,
                reported_by=self.state.user_id,
                category=key,
                description=self.note.text().strip() or None,
                photo_path=photo,
            )

    def _store_photo(self) -> str | None:
        import shutil
        from pathlib import Path

        from ...util import now_iso

        try:
            dest_dir = self.state.cfg.incidents_dir
            dest_dir.mkdir(parents=True, exist_ok=True)
            src = Path(self.photo_path)
            dest = dest_dir / f"{now_iso().replace(':', '')}_{src.name}"
            shutil.copy2(src, dest)
            return str(dest)
        except OSError:
            return self.photo_path

    def auto_fill(self) -> None:
        self._set_choice(True)


class IssuesPage(WizardPage):
    title = "Known issues on this microscope"
    short = "Notices"

    def build(self) -> None:
        self.cards_box = QVBoxLayout()
        self.cards_box.setSpacing(8)
        self.layout_.addLayout(self.cards_box)
        self.more_label = QLabel("")
        self.more_label.setObjectName("caption")
        self.layout_.addWidget(self.more_label)
        self.layout_.addStretch(1)

    def refresh(self) -> None:
        while self.cards_box.count():
            item = self.cards_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.more_label.setText("")
        rows = repo.open_incidents(self.state.conn)
        if not rows:
            self.cards_box.addWidget(
                EmptyState("No open issues — have a good session!")
            )
            return
        for r in rows[:6]:
            desc = r["description"] or r["category"].replace("_", " ")
            reporter = r["reporter_name"] or "unknown"
            meta = f"{fmt_dt(r['created_at'], '%d %b')} · {reporter}"
            severity = r["severity"] if "severity" in r.keys() else None
            self.cards_box.addWidget(ListCard(desc, meta, severity=severity))
        if len(rows) > 6:
            self.more_label.setText(f"…and {len(rows) - 6} more on the dashboard.")

    def auto_fill(self) -> None:
        pass


class SavingPage(WizardPage):
    """Final pre-use page: where to save and what happens to the files."""

    title = "You're set — here's how saving works"
    short = "Saving"

    def build(self) -> None:
        from ..ui.widgets import SectionCard

        self.card = SectionCard("While you image")
        self.dir_line = QLabel("")
        self.dir_line.setObjectName("h3")
        self.dir_line.setWordWrap(True)
        self.card.body.addWidget(self.dir_line)
        for line in (
            "When ZEN closes, AfterScope renames your files to the lab convention "
            "and files them into the shared Dropbox tree automatically.",
            "Saving into your own Dropbox folder is possible, but those files are "
            "not catalogued.",
        ):
            row = QLabel(line)
            row.setWordWrap(True)
            row.setObjectName("muted")
            self.card.body.addWidget(row)
        self.layout_.addWidget(self.card)
        self.layout_.addStretch(1)

    def refresh(self) -> None:
        row = repo.get_session(self.state.conn, self.state.session_id)
        planned = row["planned_dir"] if row and row["planned_dir"] else None
        if planned:
            self.dir_line.setText(f"Save your images into your session folder:\n{planned}")
        else:
            watch = self.state.cfg.watch_dirs
            working = str(watch[0].path) if watch else "the working directory"
            self.dir_line.setText(f"Save your images into:\n{working}")

    def auto_fill(self) -> None:
        pass


class NagOfferPage(WizardPage):
    title = "Unfinished checklist from a previous session"
    short = "Backlog"

    def build(self) -> None:
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.layout_.addWidget(self.body)
        row = QHBoxLayout()
        self.now_btn = QPushButton("Do it now (≈2 min)")
        self.now_btn.clicked.connect(self._do_now)
        self.later_btn = QPushButton("Later (logged)")
        self.later_btn.clicked.connect(self._later)
        row.addWidget(self.now_btn)
        row.addWidget(self.later_btn)
        self.layout_.addLayout(row)
        self.layout_.addStretch(1)
        self._decision = None

    def refresh(self) -> None:
        nag = self.state.sm.pending_nag()
        self._nag_id = nag["id"] if nag else None
        if nag:
            user = repo.get_user(self.state.conn, nag["user_id"]) if nag["user_id"] else None
            who = user["full_name"] if user else "someone"
            self.body.setText(
                f"The session on {fmt_dt(nag['started_at'])} ({who}) ended without its "
                "checklist. Completing it now keeps the log honest."
            )

    def _do_now(self) -> None:
        self._decision = "now"
        if self._nag_id is not None:
            self.controller.extend_with_retro(self._nag_id)
        self.controller.advance()

    def _later(self) -> None:
        self._decision = "later"
        repo.audit(self.state.conn, "nag_deferred", session_id=self._nag_id)
        self.controller.advance()

    def validate(self) -> str | None:
        if self._decision is None:
            return "Choose 'Do it now' or 'Later'."
        return None

    def auto_fill(self) -> None:
        self._decision = "later"
        repo.audit(self.state.conn, "nag_deferred", session_id=self._nag_id)
