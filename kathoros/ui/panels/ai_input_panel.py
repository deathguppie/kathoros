"""
AIInputPanel — researcher message input with agent selector and trust toggle.
No DB calls. No API calls. Emits signals only.
Parent wires message_submitted to agent dispatch layer.
"""
import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_log = logging.getLogger("kathoros.ui.panels.ai_input_panel")

_ACCESS_MODES = ["REQUEST_FIRST", "FULL_ACCESS", "NO_ACCESS"]
_ACCESS_COLORS = {
    "REQUEST_FIRST": "#f0c040",
    "FULL_ACCESS":   "#40c040",
    "NO_ACCESS":     "#f04040",
}


class _InputEdit(QPlainTextEdit):
    """QPlainTextEdit that emits enter_pressed on Enter (without Shift)."""
    enter_pressed = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.enter_pressed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class AIInputPanel(QWidget):
    message_submitted = pyqtSignal(str, str, str)
    stop_requested = pyqtSignal()
    agent_changed = pyqtSignal(str)
    access_mode_changed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._agents: list[dict] = []

        # Agent selector
        self._agent_combo = QComboBox()
        self._agent_combo.setMinimumWidth(180)
        self._agent_combo.setStyleSheet(
            "QComboBox { background: #2d2d2d; color: #cccccc; padding: 4px; }"
        )
        self._agent_combo.currentIndexChanged.connect(self._on_agent_changed)

        # Access mode toggle
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(_ACCESS_MODES)
        self._mode_combo.setCurrentText("REQUEST_FIRST")
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self._update_mode_style("REQUEST_FIRST")

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Agent:"))
        toolbar.addWidget(self._agent_combo)
        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("Access:"))
        toolbar.addWidget(self._mode_combo)
        toolbar.addStretch()

        # Message input
        self._input = _InputEdit()
        self._input.setFixedHeight(90)
        self._input.setPlaceholderText("Ask a question or give an instruction...")
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)
        self._input.setFont(font)
        self._input.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #cccccc; border: 1px solid #333; }"
        )
        self._input.enter_pressed.connect(self._on_send)

        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._on_send)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self.stop_requested)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet("QPushButton { color: #f04040; }")

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._stop_btn)
        btn_row.addWidget(send_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._input)
        layout.addLayout(btn_row)

    def load_agents(self, agents: list[dict]) -> None:
        self._agents = agents
        self._agent_combo.blockSignals(True)
        self._agent_combo.clear()
        for agent in agents:
            label = f"{agent.get('name', '?')} ({agent.get('provider', '?')})"
            self._agent_combo.addItem(label, userData=agent.get("id"))
        self._agent_combo.blockSignals(False)
        if agents:
            self._agent_combo.setCurrentIndex(0)

    def get_selected_agent_id(self) -> str | None:
        idx = self._agent_combo.currentIndex()
        if idx == -1:
            return None
        return self._agent_combo.itemData(idx)

    def get_access_mode(self) -> str:
        return self._mode_combo.currentText()

    def clear_input(self) -> None:
        self._input.clear()

    def _on_send(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return
        agent_id = self.get_selected_agent_id()
        access_mode = self.get_access_mode()
        if agent_id is None:
            _log.warning("send attempted with no agent selected")
            return
        self.message_submitted.emit(text, str(agent_id), access_mode)
        self.clear_input()

    def _on_agent_changed(self, index: int) -> None:
        agent_id = self._agent_combo.itemData(index)
        if agent_id is not None:
            self.agent_changed.emit(str(agent_id))

    def _on_mode_changed(self, mode: str) -> None:
        self._update_mode_style(mode)
        self.access_mode_changed.emit(mode)

    def _update_mode_style(self, mode: str) -> None:
        color = _ACCESS_COLORS.get(mode, "#888888")
        self._mode_combo.setStyleSheet(
            f"QComboBox {{ background: #2d2d2d; color: #cccccc; "
            f"border-left: 4px solid {color}; padding: 4px; }}"
        )

    def set_selected_agent_id(self, agent_id) -> None:
        """Select agent by DB id. No-op if not found."""
        target = str(agent_id) if agent_id is not None else None
        for i in range(self._agent_combo.count()):
            if str(self._agent_combo.itemData(i)) == target:
                self._agent_combo.setCurrentIndex(i)
                return

    def set_access_mode(self, mode: str) -> None:
        """Set access mode combo. No-op if mode not in list."""
        if mode in _ACCESS_MODES:
            self._mode_combo.setCurrentText(mode)

    def set_busy(self, busy: bool) -> None:
        self._stop_btn.setEnabled(busy)
