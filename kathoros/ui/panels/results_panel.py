"""
ResultsPanel — read-only display for tool output and query results.
Supports plain text and tabular data.
No DB calls — content loaded via show_text() or show_table().
"""
import logging
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QTableWidget, QTableWidgetItem, QStackedWidget,
    QApplication, QHeaderView
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont

_log = logging.getLogger("kathoros.ui.panels.results_panel")


class ResultsPanel(QWidget):
    clear_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._header = QLabel("Results")
        self._header.setStyleSheet("font-weight: bold; padding: 4px;")

        # Text page
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)
        self._text.setFont(font)
        self._text.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #cccccc; border: 1px solid #333; }"
        )

        # Table page
        self._table = QTableWidget()
        self._table.setStyleSheet(
            "QTableWidget { background: #1a1a1a; color: #cccccc; border: 1px solid #333; }"
            "QHeaderView::section { background: #2d2d2d; color: #cccccc; padding: 4px; }"
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setMinimumHeight(28)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._text)
        self._stack.addWidget(self._table)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear)
        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(self._copy_to_clipboard)

        toolbar = QHBoxLayout()
        toolbar.addStretch()
        toolbar.addWidget(copy_btn)
        toolbar.addWidget(clear_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._header)
        layout.addWidget(self._stack)
        layout.addLayout(toolbar)

    def show_text(self, content: str, label: str = "") -> None:
        self._stack.setCurrentWidget(self._text)
        self._text.setPlainText(content)
        ts = datetime.now().strftime("%H:%M:%S")
        self._header.setText(f"{label or 'Results'}  [{ts}]")

    def show_table(self, headers: list[str], rows: list[list]) -> None:
        self._stack.setCurrentWidget(self._table)
        self._table.setRowCount(len(rows))
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                self._table.setItem(r, c, QTableWidgetItem(str(val)))
        ts = datetime.now().strftime("%H:%M:%S")
        self._header.setText(f"Results  [{ts}]  {len(rows)} rows")

    def clear(self) -> None:
        self._text.clear()
        self._table.clearContents()
        self._table.setRowCount(0)
        self._stack.setCurrentWidget(self._text)
        self._header.setText("Results")
        self.clear_requested.emit()

    def _copy_to_clipboard(self) -> None:
        current = self._stack.currentWidget()
        if current is self._text:
            text = self._text.toPlainText()
        else:
            rows = []
            for r in range(self._table.rowCount()):
                row = []
                for c in range(self._table.columnCount()):
                    item = self._table.item(r, c)
                    row.append(item.text() if item else "")
                rows.append("\t".join(row))
            text = "\n".join(rows)
        if text:
            QApplication.clipboard().setText(text)
