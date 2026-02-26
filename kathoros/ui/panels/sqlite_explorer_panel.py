"""
SQLiteExplorerPanel — interactive SQLite query tool.
Read-only — SELECT only. No INSERT/UPDATE/DELETE/DROP allowed.
No direct DB connection ownership — connections registered via set_connection().
"""
import logging
import sqlite3

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_log = logging.getLogger("kathoros.ui.panels.sqlite_explorer_panel")


class SQLiteExplorerPanel(QWidget):
    query_executed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._connections: dict[str, sqlite3.Connection] = {}
        self._auto_queried: bool = False

        self._db_combo = QComboBox()
        self._db_combo.setStyleSheet("QComboBox { background: #2d2d2d; color: #cccccc; padding: 4px; }")

        self._sql_input = QPlainTextEdit()
        self._sql_input.setFixedHeight(90)
        self._sql_input.setPlaceholderText("SELECT * FROM objects LIMIT 20")
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)
        self._sql_input.setFont(font)
        self._sql_input.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #cccccc; border: 1px solid #333; }"
        )

        run_btn = QPushButton("Run")
        run_btn.clicked.connect(self._on_run)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear)

        spread_btn = QPushButton("Spreadsheet")
        spread_btn.clicked.connect(self._on_spreadsheet)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._db_combo)
        toolbar.addStretch()
        toolbar.addWidget(run_btn)
        toolbar.addWidget(clear_btn)
        toolbar.addWidget(spread_btn)

        self._table = QTableWidget()
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(
            "QTableWidget { background: #1e1e1e; color: #cccccc; "
            "  alternate-background-color: #252525; gridline-color: #333; }"
            "QHeaderView::section { background: #2d2d2d; color: #cccccc; padding: 4px; }"
        )

        self._status = QLabel("")
        self._status.setStyleSheet("color: #888888; padding: 2px 4px; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._sql_input)
        layout.addWidget(self._table)
        layout.addWidget(self._status)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._auto_queried and self._connections:
            self._auto_queried = True
            # Default to project DB if available
            idx = self._db_combo.findText("project")
            if idx >= 0:
                self._db_combo.setCurrentIndex(idx)
            self._sql_input.setPlainText("SELECT * FROM objects LIMIT 50")
            self.execute_query("SELECT * FROM objects LIMIT 50")

    def set_connection(self, name: str, conn: sqlite3.Connection) -> None:
        self._connections[name] = conn
        if self._db_combo.findText(name) == -1:
            self._db_combo.addItem(name)
        _log.debug("connection registered: %s", name)

    def execute_query(self, sql: str) -> None:
        name = self._db_combo.currentText()
        if not name or name not in self._connections:
            self._status.setText("No database selected.")
            return
        if not self._is_safe_query(sql):
            self._status.setText("Error: only SELECT statements allowed.")
            self._status.setStyleSheet("color: #f04040; padding: 2px 4px;")
            return
        try:
            conn = self._connections[name]
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description] if cursor.description else []

            self._table.setColumnCount(len(cols))
            self._table.setHorizontalHeaderLabels(cols)
            self._table.setRowCount(len(rows))

            for r, row in enumerate(rows):
                self._table.setRowHeight(r, 28)
                for c, val in enumerate(row):
                    self._table.setItem(r, c, QTableWidgetItem(str(val) if val is not None else ""))

            self._status.setText(f"{len(rows)} rows returned")
            self._status.setStyleSheet("color: #40c040; padding: 2px 4px; font-size: 11px;")
            self.query_executed.emit(sql)

        except sqlite3.Error as exc:
            self._table.setRowCount(0)
            self._status.setText(f"Error: {exc}")
            self._status.setStyleSheet("color: #f04040; padding: 2px 4px; font-size: 11px;")
            _log.warning("query failed: %s", exc)

    def clear(self) -> None:
        self._sql_input.clear()
        self._table.setRowCount(0)
        self._table.setColumnCount(0)
        self._status.setText("")
        self._status.setStyleSheet("color: #888888; padding: 2px 4px; font-size: 11px;")

    def _is_safe_query(self, sql: str) -> bool:
        return sql.strip().lower().startswith("select")

    def _on_spreadsheet(self) -> None:
        from kathoros.ui.dialogs.sqlite_spreadsheet_dialog import SQLiteSpreadsheetDialog
        dlg = SQLiteSpreadsheetDialog(self._connections, self)
        dlg.exec()
        # Refresh current query after dialog closes
        sql = self._sql_input.toPlainText().strip()
        if sql:
            self.execute_query(sql)

    def _on_run(self) -> None:
        sql = self._sql_input.toPlainText().strip()
        if sql:
            self.execute_query(sql)
