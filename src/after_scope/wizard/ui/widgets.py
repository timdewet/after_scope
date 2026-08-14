"""Reusable wizard widgets: chip groups, section cards, stat tiles, list cards.

Design rule for chips: they are quick-input for a *canonical text field*, not a
parallel data model. Clicking a chip inserts/removes its token in the target
QLineEdit; the field stays free-editable and remains the single source of truth
(so tests, save() code and power users all read/write plain text).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import tokens as t
from .tokens import active


def _tokens_of(text: str) -> list[str]:
    return [p.strip() for p in text.split(",") if p.strip()]


class ChipGroup(QWidget):
    """A row of toggleable pill buttons.

    With a `target` QLineEdit: checking inserts the chip's token into the
    comma-separated field, unchecking removes it; chip state re-syncs whenever
    the field changes. `exclusive=True` keeps at most one chip's token present.

    Without a target: a standalone picker — read `selected()`.
    """

    def __init__(
        self,
        options: list[str],
        target: QLineEdit | None = None,
        exclusive: bool = False,
    ) -> None:
        super().__init__()
        self.target = target
        self.exclusive = exclusive
        self._syncing = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.S2)
        self.chips: dict[str, QPushButton] = {}
        for option in options:
            chip = QPushButton(option)
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _=False, o=option: self._chip_clicked(o))
            self.chips[option] = chip
            layout.addWidget(chip)
        layout.addStretch(1)
        if target is not None:
            target.textChanged.connect(self._sync_from_text)
            self._sync_from_text(target.text())

    # -- with target ------------------------------------------------------------

    def _chip_clicked(self, option: str) -> None:
        if self.target is None:
            if self.exclusive:
                for name, chip in self.chips.items():
                    if name != option:
                        chip.setChecked(False)
            return
        tokens = _tokens_of(self.target.text())
        if self.chips[option].isChecked():
            if self.exclusive:
                tokens = [tok for tok in tokens if tok not in self.chips]
            if option not in tokens:
                tokens.append(option)
        else:
            tokens = [tok for tok in tokens if tok != option]
        self._syncing = True
        self.target.setText(", ".join(tokens))
        self._syncing = False
        self._sync_from_text(self.target.text())

    def _sync_from_text(self, text: str) -> None:
        if self._syncing:
            return
        tokens = set(_tokens_of(text))
        for name, chip in self.chips.items():
            chip.setChecked(name in tokens)

    # -- standalone -------------------------------------------------------------

    def selected(self) -> list[str]:
        return [name for name, chip in self.chips.items() if chip.isChecked()]

    def value(self) -> str | None:
        picked = self.selected()
        return picked[0] if picked else None

    def set_value(self, option: str | None) -> None:
        for name, chip in self.chips.items():
            chip.setChecked(name == option)


class SectionCard(QFrame):
    """A titled card: h3 title, optional caption, then caller-added content."""

    def __init__(self, title: str, caption: str | None = None) -> None:
        super().__init__()
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(t.S5, t.S4, t.S5, t.S5)
        outer.setSpacing(t.S3)
        head = QLabel(title)
        head.setObjectName("h3")
        outer.addWidget(head)
        if caption:
            cap = QLabel(caption)
            cap.setObjectName("caption")
            cap.setWordWrap(True)
            outer.addWidget(cap)
        self.body = outer

    def add_field(self, label: str, *widgets: QWidget) -> None:
        """A labelled block: caption label above the widget(s)."""
        cap = QLabel(label)
        cap.setObjectName("fieldLabel")
        self.body.addWidget(cap)
        for w in widgets:
            self.body.addWidget(w)


class StatTile(QFrame):
    """Big value over a small caption — for the summary page."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        v = QVBoxLayout(self)
        v.setContentsMargins(t.S5, t.S4, t.S5, t.S4)
        v.setSpacing(t.S1)
        self.value_label = QLabel("—")
        self.value_label.setObjectName("statValue")
        cap = QLabel(label)
        cap.setObjectName("caption")
        v.addWidget(self.value_label)
        v.addWidget(cap)

    def set_value(self, value: str, good: bool | None = None) -> None:
        self.value_label.setText(value)
        p = active()
        color = p.text if good is None else (p.success if good else p.warning)
        self.value_label.setStyleSheet(f"color: {color};")


SEVERITY_COLORS = {  # resolved against the active palette at draw time
    "minor": "warning",
    "major": "danger",
    "blocking": "danger",
}


class ListCard(QFrame):
    """A compact card row: colored dot, bold title, muted meta line."""

    def __init__(self, title: str, meta: str, severity: str | None = None) -> None:
        super().__init__()
        self.setObjectName("card")
        p = active()
        row = QHBoxLayout(self)
        row.setContentsMargins(t.S4, t.S3, t.S4, t.S3)
        row.setSpacing(t.S3)
        dot = QFrame()
        dot.setFixedSize(10, 10)
        color = getattr(p, SEVERITY_COLORS.get(severity or "", ""), p.text_subtle)
        dot.setStyleSheet(f"background: {color}; border-radius: 5px;")
        row.addWidget(dot, alignment=Qt.AlignTop)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        title_label.setWordWrap(True)
        meta_label = QLabel(meta)
        meta_label.setObjectName("caption")
        text_col.addWidget(title_label)
        text_col.addWidget(meta_label)
        row.addLayout(text_col, stretch=1)


class EmptyState(QLabel):
    """Centered friendly placeholder for lists with nothing to show."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setObjectName("emptyState")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
