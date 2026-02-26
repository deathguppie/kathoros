"""
SageMathPanel — interactive SageMath evaluator via conda subprocess.
Runs in QThread to avoid blocking UI.
No DB calls.
"""
import logging
import subprocess

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

_log = logging.getLogger("kathoros.ui.panels.sagemath_panel")


class _SageWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, expression: str) -> None:
        super().__init__()
        self._expression = expression

    def run(self) -> None:
        code = f"from sage.all import *\n{self._expression}"
        try:
            result = subprocess.run(
                ["conda", "run", "-n", "sage", "sage", "-c", code],
                timeout=30,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                self.error.emit(result.stderr.strip() or "Unknown error")
            else:
                self.finished.emit(result.stdout.strip())
        except subprocess.TimeoutExpired:
            self.error.emit("Evaluation timed out (30s)")
        except Exception as exc:
            self.error.emit(str(exc))


class SageMathPanel(QWidget):
    result_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker = None

        header = QLabel("SageMath 10.5")
        header.setStyleSheet("font-weight: bold; padding: 4px;")

        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)

        self._input = QPlainTextEdit()
        self._input.setFixedHeight(90)
        self._input.setPlaceholderText("factor(x^2 - 1)")
        self._input.setFont(font)
        self._input.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #cccccc; border: 1px solid #333; }"
        )

        self._eval_btn = QPushButton("Evaluate")
        self._eval_btn.clicked.connect(self.evaluate)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._eval_btn)
        toolbar.addWidget(clear_btn)
        toolbar.addStretch()

        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(font)
        self._output.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #cccccc; border: 1px solid #333; }"
        )

        self._status = QLabel("Ready")
        self._status.setStyleSheet("color: #888888; padding: 2px 4px; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(header)
        layout.addWidget(self._input)
        layout.addLayout(toolbar)
        layout.addWidget(self._output)
        layout.addWidget(self._status)

    def evaluate(self, expression: str = "") -> None:
        expr = expression or self._input.toPlainText().strip()
        if not expr:
            return
        self._eval_btn.setEnabled(False)
        self._status.setText("Running...")
        self._worker = _SageWorker(expr)
        self._worker.finished.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def clear(self) -> None:
        self._input.clear()
        self._output.clear()
        self._status.setText("Ready")
        self._status.setStyleSheet("color: #888888; padding: 2px 4px; font-size: 11px;")

    def _on_result(self, result: str) -> None:
        self._append_output(result, "#cccccc")
        self._status.setText("Done")
        self._status.setStyleSheet("color: #40c040; padding: 2px 4px; font-size: 11px;")
        self._eval_btn.setEnabled(True)
        self.result_ready.emit(result)

    def _on_error(self, error: str) -> None:
        self._append_output(f"Error: {error}", "#f04040")
        self._status.setText("Error")
        self._status.setStyleSheet("color: #f04040; padding: 2px 4px; font-size: 11px;")
        self._eval_btn.setEnabled(True)
        self.error_occurred.emit(error)

    def _append_output(self, text: str, color: str) -> None:
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if self._output.toPlainText():
            cursor.insertText("\n", fmt)
        cursor.insertText(text, fmt)
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()
