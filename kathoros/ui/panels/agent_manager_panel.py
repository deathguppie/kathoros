"""
AgentManagerPanel — view and manage agents from global registry.
No DB calls — receives data via load_agents(), emits changes via signals.
"""
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor

_log = logging.getLogger("kathoros.ui.panels.agent_manager_panel")

_TRUST_COLORS = {
    "untrusted": "#f04040",
    "monitored": "#f0c040",
    "trusted":   "#40c040",
}

_COLUMNS = ["name", "type", "provider", "model_string", "trust_level", "cost_tier", "is_active"]
_HEADERS = ["Name", "Type", "Provider", "Model", "Trust", "Cost", "Active"]


class AgentManagerPanel(QWidget):
    agent_selected = pyqtSignal(int)
    add_agent_requested = pyqtSignal()
    edit_agent_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)
    refresh_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._agent_ids: list[int] = []

        self._header = QLabel("Agents (0)")
        self._header.setStyleSheet("font-weight: bold; padding: 4px;")

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(
            "QTableWidget { background: #1e1e1e; color: #cccccc; "
            "  alternate-background-color: #252525; gridline-color: #333; }"
            "QHeaderView::section { background: #2d2d2d; color: #cccccc; padding: 4px; }"
            "QTableWidget::item { min-height: 28px; }"
        )
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        _btn_style = (
            "QPushButton { background: #2d2d2d; color: #cccccc; border: 1px solid #555; "
            "padding: 4px 12px; min-height: 24px; } "
            "QPushButton:hover { background: #3d3d3d; }"
        )
        add_btn = QPushButton("+ Add Agent")
        add_btn.setStyleSheet(_btn_style)
        add_btn.clicked.connect(self.add_agent_requested)
        edit_btn = QPushButton("Edit")
        edit_btn.setStyleSheet(_btn_style)
        edit_btn.clicked.connect(self._on_edit)
        delete_btn = QPushButton("Delete")
        delete_btn.setStyleSheet(
            "QPushButton { background: #2d2d2d; color: #f04040; border: 1px solid #555; "
            "padding: 4px 12px; min-height: 24px; } "
            "QPushButton:hover { background: #3d3d3d; }"
        )
        delete_btn.clicked.connect(self._on_delete)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_btn_style)
        refresh_btn.clicked.connect(self.refresh_requested)

        toolbar = QHBoxLayout()
        toolbar.addWidget(add_btn)
        toolbar.addWidget(edit_btn)
        toolbar.addWidget(delete_btn)
        toolbar.addStretch()
        toolbar.addWidget(refresh_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._header)
        layout.addWidget(self._table)
        layout.addLayout(toolbar)

    def load_agents(self, agents: list[dict]) -> None:
        self._table.setRowCount(0)
        self._agent_ids = []
        for agent in agents:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setRowHeight(row, 28)
            self._agent_ids.append(agent.get("id"))
            for col, key in enumerate(_COLUMNS):
                val = agent.get(key, "")
                if key == "is_active":
                    val = "✓" if val else "—"
                item = QTableWidgetItem(str(val) if val is not None else "")
                if key == "trust_level":
                    color = _TRUST_COLORS.get(str(val).lower(), "#888888")
                    item.setForeground(QColor(color))
                item.setData(Qt.ItemDataRole.UserRole, agent.get("id"))
                self._table.setItem(row, col, item)
        self._header.setText(f"Agents ({len(agents)})")

    def get_selected_id(self) -> int | None:
        rows = self._table.selectedItems()
        if rows:
            return rows[0].data(Qt.ItemDataRole.UserRole)
        return None

    def clear(self) -> None:
        self._table.setRowCount(0)
        self._agent_ids = []
        self._header.setText("Agents (0)")

    def _on_selection_changed(self) -> None:
        agent_id = self.get_selected_id()
        if agent_id is not None:
            self.agent_selected.emit(agent_id)

    def _on_edit(self) -> None:
        agent_id = self.get_selected_id()
        if agent_id is not None:
            self.edit_agent_requested.emit(agent_id)

    def _on_delete(self) -> None:
        agent_id = self.get_selected_id()
        if agent_id is not None:
            self.delete_requested.emit(agent_id)
