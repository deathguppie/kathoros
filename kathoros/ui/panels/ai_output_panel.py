"""
AIOutputPanel — streaming AI response display.
Read-only. Content appended via append_text() and append_tool_request().
No DB calls.
"""
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor

_log = logging.getLogger("kathoros.ui.panels.ai_output_panel")


class AIOutputPanel(QWidget):
    clear_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._in_think_block = False
        self._in_stream = False

        self._header = QLabel("AI Output")
        self._header.setStyleSheet("font-weight: bold; padding: 4px;")

        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)
        self._output.setFont(font)
        self._output.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #cccccc; border: 1px solid #333; }"
        )

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._header)
        toolbar.addStretch()
        toolbar.addWidget(clear_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._output)

    def append_text(self, text: str, role: str = "assistant") -> None:
        if role == "assistant":
            text = self._filter_think(text)
            if not text:
                return
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        if role == "user":
            fmt.setForeground(QColor("#4090f0"))
        elif role == "assistant":
            fmt.setForeground(QColor("#cccccc"))
        elif role == "system":
            fmt.setForeground(QColor("#888888"))
        else:
            fmt.setForeground(QColor("#cccccc"))
        if self._output.toPlainText() and not self._in_stream:
            cursor.insertText("\n", fmt)
        self._in_stream = True
        cursor.insertText(text, fmt)
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()

    def _filter_think(self, text: str) -> str:
        """Strip <think>...</think> blocks from streaming chunks."""
        result = []
        i = 0
        while i < len(text):
            if not self._in_think_block:
                start = text.find("<think>", i)
                if start == -1:
                    result.append(text[i:])
                    break
                result.append(text[i:start])
                self._in_think_block = True
                i = start + 7
            else:
                end = text.find("</think>", i)
                if end == -1:
                    break  # still inside think block
                self._in_think_block = False
                i = end + 8
        return "".join(result)

    def append_tool_request(self, tool_name: str, summary: str) -> None:
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#f0c040"))
        if self._output.toPlainText():
            cursor.insertText("\n", fmt)
        cursor.insertText(f"[TOOL REQUEST] {tool_name}: {summary}", fmt)
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()
        self._in_stream = False

    def clear(self) -> None:
        self._output.clear()
        self._in_stream = False
        self._in_think_block = False
        self.clear_requested.emit()
