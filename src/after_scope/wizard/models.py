"""Qt table model for the session's files with batch metadata editing."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QPixmap

from ..db import repo

COLUMNS = [
    ("thumb", ""),
    ("name", "File"),
    ("acquired", "Acquired"),
    ("objective", "Objective"),
    ("channels", "Channels"),
    ("experiment", "Experiment"),
    ("strain", "Strain"),
    ("condition", "Condition"),
    ("coverslip", "Coverslip / prep"),
    ("notes", "Notes"),
    ("junk", "Junk"),
]
EDITABLE = {"experiment", "strain", "condition", "coverslip", "notes"}
_COL_KEYS = [c[0] for c in COLUMNS]


class SessionFilesModel(QAbstractTableModel):
    def __init__(self, conn: sqlite3.Connection, session_id: int) -> None:
        super().__init__()
        self.conn = conn
        self.session_id = session_id
        self.rows: list[dict] = []
        self._thumb_cache: dict[str, QPixmap] = {}
        self.reload()

    # -- loading --------------------------------------------------------------------

    def reload(self) -> None:
        self.beginResetModel()
        self.rows = []
        for r in repo.session_files(self.conn, self.session_id):
            if r["status"] == "dust_ref":
                continue  # dust references are handled on their own page
            exp_name = ""
            if r["experiment_id"]:
                row = self.conn.execute(
                    "SELECT name FROM experiments WHERE id=?", (r["experiment_id"],)
                ).fetchone()
                exp_name = row["name"] if row else ""
            channels = ""
            if r["channels_json"]:
                import json

                names = [c.get("name", "?") for c in json.loads(r["channels_json"])]
                channels = ", ".join(n for n in names if n)
            self.rows.append(
                {
                    "file_id": r["id"],
                    "name": r["current_path"].rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
                    "acquired": (r["acquired_at"] or "")[11:16],
                    "objective": r["objective_name"] or "",
                    "channels": channels,
                    "thumb": r["thumbnail_path"],
                    "experiment": exp_name,
                    "strain": r["strain"] or "",
                    "condition": r["condition"] or "",
                    "coverslip": r["coverslip"] or "",
                    "notes": r["notes"] or "",
                    "junk": r["status"] == "excluded",
                }
            )
        self.endResetModel()

    # -- Qt model API ---------------------------------------------------------------

    def rowCount(self, parent=None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self.rows)

    def columnCount(self, parent=None) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section][1]
        return None

    def flags(self, index: QModelIndex):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        key = _COL_KEYS[index.column()]
        if key in EDITABLE:
            return base | Qt.ItemIsEditable
        if key == "junk":
            return base | Qt.ItemIsUserCheckable
        return base

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        row = self.rows[index.row()]
        key = _COL_KEYS[index.column()]
        if key == "thumb":
            if role == Qt.DecorationRole and row["thumb"]:
                pm = self._thumb_cache.get(row["thumb"])
                if pm is None:
                    pm = QPixmap(row["thumb"]).scaledToHeight(
                        40, Qt.SmoothTransformation
                    )
                    self._thumb_cache[row["thumb"]] = pm
                return pm
            return None
        if key == "junk":
            if role == Qt.CheckStateRole:
                return Qt.Checked if row["junk"] else Qt.Unchecked
            return None
        if role in (Qt.DisplayRole, Qt.EditRole):
            return row[key]
        return None

    def setData(self, index: QModelIndex, value, role=Qt.EditRole) -> bool:
        row = self.rows[index.row()]
        key = _COL_KEYS[index.column()]
        if key == "junk" and role == Qt.CheckStateRole:
            row["junk"] = value in (Qt.Checked, Qt.Checked.value)
            self.dataChanged.emit(index, index)
            return True
        if key in EDITABLE and role == Qt.EditRole:
            row[key] = str(value).strip()
            self.dataChanged.emit(index, index)
            return True
        return False

    # -- batch + persistence ---------------------------------------------------------

    def apply_batch(self, row_indices: list[int], **fields: str) -> None:
        targets = row_indices or range(len(self.rows))
        for i in targets:
            for k, v in fields.items():
                if v:
                    self.rows[i][k] = v
        if self.rows:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self.rows) - 1, len(COLUMNS) - 1)
            )

    def save_to_db(self, user_id: int | None) -> None:
        for row in self.rows:
            experiment_id = None
            if row["experiment"]:
                experiment_id = repo.get_or_create_experiment(
                    self.conn, row["experiment"], user_id
                )
            repo.set_file_user_meta(
                self.conn,
                row["file_id"],
                experiment_id=experiment_id,
                user_id=user_id,
                strain=row["strain"] or None,
                condition=row["condition"] or None,
                coverslip=row["coverslip"] or None,
                notes=row["notes"] or None,
            )
            current = repo.get_file(self.conn, row["file_id"])
            if row["junk"] and current["status"] != "excluded":
                repo.set_file_status(self.conn, row["file_id"], "excluded")
            elif not row["junk"] and current["status"] == "excluded":
                repo.set_file_status(self.conn, row["file_id"], "new")
