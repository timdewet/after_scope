"""Naming & organization page: proposed standardized names/destinations, then execute."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem

from ...dustref import register_session_dust_refs
from ...metadata.organize import execute_plans, plan_moves
from .base import WizardPage


class NamingPage(WizardPage):
    title = "Filing your images"

    def build(self) -> None:
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.layout_.addWidget(self.info)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Current file", "New name & location", "Leave in place"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.layout_.addWidget(self.table, stretch=1)

    def refresh(self) -> None:
        self.plans = plan_moves(self.state.conn, self.state.session_id, self.state.cfg)
        mode = self.state.cfg.organize.mode
        if mode == "index_only":
            self.info.setText("Files stay where you saved them; only the catalog records them.")
        else:
            verb = "moved" if mode == "move" else "copied"
            self.info.setText(
                f"Files will be renamed to the lab convention and {verb} into the shared "
                "Dropbox tree. Untick any file you want to leave where it is."
            )
        self.table.setRowCount(len(self.plans))
        for i, plan in enumerate(self.plans):
            src_item = QTableWidgetItem(plan.src.name)
            src_item.setFlags(Qt.ItemIsEnabled)
            dst_item = QTableWidgetItem(str(plan.dst))
            dst_item.setFlags(Qt.ItemIsEnabled)
            keep = QTableWidgetItem()
            keep.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            keep.setCheckState(Qt.Unchecked)
            self.table.setItem(i, 0, src_item)
            self.table.setItem(i, 1, dst_item)
            self.table.setItem(i, 2, keep)
        self.table.resizeColumnsToContents()

    def save(self) -> None:
        for i, plan in enumerate(self.plans):
            item = self.table.item(i, 2)
            if item is not None and item.checkState() == Qt.Checked:
                plan.action = "index_only"
        execute_plans(self.state.conn, self.plans)
        register_session_dust_refs(self.state.conn, self.state.session_id)

    def auto_fill(self) -> None:
        pass  # accept all proposals
