"""
SQLiteSpreadsheetDialog — fullscreen editable spreadsheet for SQLite tables.
Launched from SQLiteExplorerPanel. Supports cell editing, row add/delete,
and batch save via UPDATE statements keyed on rowid.
"""
import logging
import sqlite3

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QComboBox,
    QHeaderView, QAbstractItemView, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

_log = logging.getLogger("kathoros.ui.dialogs.sqlite_spreadsheet_dialog")

_DIRTY_BG = QColor("#4a4a20")
_EDITABLE_COLUMNS = {"name", "tags"}

_STYLE = """
QDialog        { background: #1e1e1e; color: #cccccc; }
QTableWidget   { background: #1e1e1e; color: #cccccc;
                 alternate-background-color: #252525; gridline-color: #333; }
QHeaderView::section { background: #2d2d2d; color: #cccccc; padding: 4px; }
QComboBox      { background: #2d2d2d; color: #cccccc; padding: 4px; }
QLineEdit      { background: #1a1a1a; color: #cccccc; border: 1px solid #333; padding: 4px; }
QPushButton    { background: #2d2d2d; color: #cccccc; padding: 4px 12px;
                 border: 1px solid #444; border-radius: 3px; }
QPushButton:hover { background: #3d3d3d; }
QLabel         { color: #888888; }
"""


class SQLiteSpreadsheetDialog(QDialog):
    """Fullscreen editable spreadsheet over a SQLite connection."""

    def __init__(self, connections: dict[str, sqlite3.Connection], parent=None) -> None:
        super().__init__(parent)
        self._connections = connections
        self._current_table: str = ""
        self._columns: list[str] = []
        self._rowids: list[int] = []
        self._dirty: dict[tuple[int, int], str] = {}  # (row, col) -> original value
        self._loading = False

        self.setWindowTitle("SQLite Spreadsheet")
        self.setStyleSheet(_STYLE)
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # -- toolbar --
        toolbar = QHBoxLayout()

        self._db_combo = QComboBox()
        self._db_combo.addItems(self._connections.keys())
        self._db_combo.currentTextChanged.connect(self._on_db_changed)
        toolbar.addWidget(QLabel("DB:"))
        toolbar.addWidget(self._db_combo)

        self._table_combo = QComboBox()
        self._table_combo.currentTextChanged.connect(self._on_table_selected)
        toolbar.addWidget(QLabel("Table:"))
        toolbar.addWidget(self._table_combo)

        toolbar.addSpacing(12)

        self._sql_input = QLineEdit()
        self._sql_input.setPlaceholderText("Custom SQL (SELECT only)…")
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)
        self._sql_input.setFont(font)
        self._sql_input.returnPressed.connect(self._on_run_sql)
        toolbar.addWidget(self._sql_input, stretch=1)

        run_btn = QPushButton("Run")
        run_btn.clicked.connect(self._on_run_sql)
        toolbar.addWidget(run_btn)

        toolbar.addSpacing(12)

        add_btn = QPushButton("+ Row")
        add_btn.clicked.connect(self._on_add_row)
        toolbar.addWidget(add_btn)

        del_btn = QPushButton("Delete Row")
        del_btn.clicked.connect(self._on_delete_rows)
        toolbar.addWidget(del_btn)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        toolbar.addWidget(save_btn)

        layout.addLayout(toolbar)

        # -- spreadsheet --
        self._grid = QTableWidget()
        self._grid.setAlternatingRowColors(True)
        self._grid.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self._grid.horizontalHeader().setStretchLastSection(True)
        self._grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._grid.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._grid.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self._grid)

        # -- status bar --
        self._status = QLabel("")
        self._status.setStyleSheet("color: #888888; padding: 2px 4px; font-size: 11px;")
        layout.addWidget(self._status)

        # populate tables for first DB
        if self._db_combo.count():
            self._on_db_changed(self._db_combo.currentText())

    # ── helpers ───────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection | None:
        name = self._db_combo.currentText()
        return self._connections.get(name)

    def _set_status(self, text: str, error: bool = False) -> None:
        color = "#f04040" if error else "#40c040"
        self._status.setStyleSheet(f"color: {color}; padding: 2px 4px; font-size: 11px;")
        self._status.setText(text)

    def _update_status_counts(self) -> None:
        rows = self._grid.rowCount()
        dirty = len(self._dirty)
        parts = [f"{rows} rows"]
        if dirty:
            parts.append(f"{dirty} modified")
        self._set_status(" | ".join(parts))

    # ── DB / table selection ─────────────────────────────────────────

    def _on_db_changed(self, name: str) -> None:
        conn = self._connections.get(name)
        if not conn:
            return
        self._table_combo.blockSignals(True)
        self._table_combo.clear()
        try:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [r[0] for r in cur.fetchall()]
            self._table_combo.addItems(tables)
        except sqlite3.Error as exc:
            _log.warning("failed to list tables: %s", exc)
        finally:
            self._table_combo.blockSignals(False)
        if self._table_combo.count():
            self._on_table_selected(self._table_combo.currentText())

    def _on_table_selected(self, table: str) -> None:
        if not table:
            return
        self._current_table = table
        self._sql_input.clear()
        self._load_table(table)

    def _load_table(self, table: str) -> None:
        conn = self._conn()
        if not conn:
            return
        # Use quoted identifier to prevent injection
        safe = table.replace('"', '""')
        sql = f'SELECT rowid, * FROM "{safe}" LIMIT 500'
        try:
            cur = conn.execute(sql)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        except sqlite3.Error as exc:
            self._set_status(f"Error: {exc}", error=True)
            return

        # cols[0] is rowid — hide it but store for writes
        self._rowids = [row[0] for row in rows]
        self._columns = cols[1:]  # visible columns

        self._loading = True
        self._dirty.clear()
        self._grid.setColumnCount(len(self._columns))
        self._grid.setHorizontalHeaderLabels(self._columns)
        self._grid.setRowCount(len(rows))

        for r, row in enumerate(rows):
            self._grid.setRowHeight(r, 28)
            for c, val in enumerate(row[1:]):  # skip rowid
                item = QTableWidgetItem(str(val) if val is not None else "")
                if self._columns[c].lower() not in _EDITABLE_COLUMNS:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._grid.setItem(r, c, item)

        self._loading = False
        self._update_status_counts()

    # ── custom SQL ───────────────────────────────────────────────────

    def _on_run_sql(self) -> None:
        sql = self._sql_input.text().strip()
        if not sql:
            return
        if not sql.lower().startswith("select"):
            self._set_status("Only SELECT queries allowed in SQL input.", error=True)
            return
        conn = self._conn()
        if not conn:
            return

        self._current_table = ""  # disable writes for custom queries
        try:
            cur = conn.execute(sql)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        except sqlite3.Error as exc:
            self._set_status(f"Error: {exc}", error=True)
            return

        self._loading = True
        self._dirty.clear()
        self._rowids.clear()
        self._columns = cols
        self._grid.setColumnCount(len(cols))
        self._grid.setHorizontalHeaderLabels(cols)
        self._grid.setRowCount(len(rows))

        # Check if first col is rowid
        has_rowid = cols and cols[0] == "rowid"
        start_col = 1 if has_rowid else 0
        display_cols = cols[start_col:]

        if has_rowid:
            self._rowids = [row[0] for row in rows]
            self._columns = display_cols
            self._grid.setColumnCount(len(display_cols))
            self._grid.setHorizontalHeaderLabels(display_cols)

        for r, row in enumerate(rows):
            self._grid.setRowHeight(r, 28)
            for c, val in enumerate(row[start_col:]):
                item = QTableWidgetItem(str(val) if val is not None else "")
                col_name = self._columns[c].lower() if c < len(self._columns) else ""
                if col_name not in _EDITABLE_COLUMNS:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._grid.setItem(r, c, item)

        self._loading = False
        self._update_status_counts()

    # ── cell editing ─────────────────────────────────────────────────

    def _on_cell_changed(self, row: int, col: int) -> None:
        if self._loading:
            return
        key = (row, col)
        item = self._grid.item(row, col)
        if not item:
            return
        # Record original value on first edit
        if key not in self._dirty:
            self._dirty[key] = ""  # we don't have original cached separately
        item.setBackground(_DIRTY_BG)
        self._update_status_counts()

    # ── save ─────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        if not self._dirty:
            self._set_status("Nothing to save.")
            return
        if not self._current_table:
            self._set_status("Cannot save: no table selected (custom query).", error=True)
            return
        if not self._rowids:
            self._set_status("Cannot save: no rowid mapping.", error=True)
            return
        conn = self._conn()
        if not conn:
            return

        safe_table = self._current_table.replace('"', '""')
        errors = []
        try:
            conn.execute("BEGIN")
            for (row, col), _ in self._dirty.items():
                if row >= len(self._rowids):
                    continue
                rid = self._rowids[row]
                col_name = self._columns[col].replace('"', '""')
                new_val = self._grid.item(row, col).text()
                try:
                    conn.execute(
                        f'UPDATE "{safe_table}" SET "{col_name}" = ? WHERE rowid = ?',
                        (new_val, rid),
                    )
                except sqlite3.Error as exc:
                    errors.append(f"row {row}: {exc}")
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            self._set_status(f"Transaction error: {exc}", error=True)
            return

        if errors:
            self._set_status(f"Saved with {len(errors)} errors: {errors[0]}", error=True)
        else:
            count = len(self._dirty)
            self._dirty.clear()
            self._set_status(f"Saved {count} change(s).")
            # Reload to clear highlights and refresh data
            self._load_table(self._current_table)

    # ── add / delete rows ────────────────────────────────────────────

    def _on_add_row(self) -> None:
        if not self._current_table:
            self._set_status("Select a table first.", error=True)
            return
        conn = self._conn()
        if not conn:
            return
        safe = self._current_table.replace('"', '""')
        try:
            conn.execute(f'INSERT INTO "{safe}" DEFAULT VALUES')
            conn.commit()
            self._load_table(self._current_table)
            self._set_status("Row added.")
        except sqlite3.Error as exc:
            self._set_status(f"Add row failed: {exc}", error=True)

    def _on_delete_rows(self) -> None:
        if not self._current_table:
            self._set_status("Select a table first.", error=True)
            return
        selected = self._grid.selectionModel().selectedRows()
        if not selected:
            self._set_status("Select row(s) to delete.", error=True)
            return
        conn = self._conn()
        if not conn:
            return

        row_indices = sorted(set(idx.row() for idx in selected), reverse=True)
        rids = [self._rowids[r] for r in row_indices if r < len(self._rowids)]
        if not rids:
            return

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete {len(rids)} row(s)? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        safe = self._current_table.replace('"', '""')
        try:
            for rid in rids:
                conn.execute(f'DELETE FROM "{safe}" WHERE rowid = ?', (rid,))
            conn.commit()
            self._load_table(self._current_table)
            self._set_status(f"Deleted {len(rids)} row(s).")
        except sqlite3.Error as exc:
            self._set_status(f"Delete failed: {exc}", error=True)

    # ── open maximized ───────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.showMaximized()
