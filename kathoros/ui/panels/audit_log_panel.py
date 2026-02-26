"""
AuditLogPanel — read-only interaction log for current session.
No DB calls — receives data via load_interactions().
UI must not import db.queries directly.
"""
import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

_log = logging.getLogger("kathoros.ui.panels.audit_log_panel")

_ROLE = {
    "user":      ("▶", "#4090f0"),
    "assistant": ("◆", "#40c040"),
}


class AuditLogPanel(QWidget):
    refresh_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._header = QLabel("Audit Log (0)")
        self._header.setStyleSheet("font-weight: bold; padding: 4px;")

        self._list = QListWidget()
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._list.setFont(mono)
        self._list.setStyleSheet(
            "QListWidget { background: #252525; border: 1px solid #333; }"
            "QListWidget::item { min-height: 28px; padding: 2px 4px; }"
            "QListWidget::item:selected { background: #3d3d3d; }"
        )

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_requested)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._header)
        layout.addWidget(self._list)
        layout.addWidget(refresh_btn)

    def load_interactions(self, interactions: list[dict]) -> None:
        self._list.clear()
        for interaction in interactions:
            text, color = self._format_row(interaction)
            item = QListWidgetItem(text)
            item.setForeground(QColor(color))
            item.setData(Qt.ItemDataRole.UserRole, interaction.get("id"))
            self._list.addItem(item)
        self._header.setText(f"Audit Log ({len(interactions)})")

    def clear(self) -> None:
        self._list.clear()
        self._header.setText("Audit Log (0)")

    def _format_row(self, interaction: dict) -> tuple[str, str]:
        role = str(interaction.get("role", "")).lower()
        icon, color = _ROLE.get(role, ("?", "#888888"))
        ts = str(interaction.get("timestamp", ""))[:19]
        content = str(interaction.get("content", ""))
        preview = content[:80] + "…" if len(content) > 80 else content
        return f"{icon}  {ts}  {preview}", color
