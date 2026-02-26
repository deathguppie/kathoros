"""
CrossProjectSearchPanel — FTS search across one or all project DBs.

Search runs in a QThread worker so the UI stays responsive.
PM is injected via set_project_manager() after construction.
"""
import logging

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_log = logging.getLogger("kathoros.ui.panels.cross_project_search_panel")

_COL_PROJECT, _COL_NAME, _COL_TYPE, _COL_STATUS, _COL_SNIPPET = range(5)
_HEADERS = ["Project", "Name", "Type", "Status", "Snippet"]


class _SearchWorker(QThread):
    results_ready = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, scope: str, query: str, pm) -> None:
        super().__init__()
        self._scope = scope
        self._query = query
        self._pm = pm

    def run(self) -> None:
        try:
            if self._scope == "current":
                import sqlite3

                from kathoros.services.search_service import search_current_project
                root = self._pm.project_root
                if root is None:
                    self.results_ready.emit([])
                    return
                db_path = root / "project.db"
                if not db_path.exists():
                    self.results_ready.emit([])
                    return
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                name = self._pm.project_name or ""
                results = search_current_project(conn, self._query, project_name=name)
                conn.close()
            else:
                from kathoros.services.project_manager import PROJECTS_DIR
                from kathoros.services.search_service import search_all_projects
                results = search_all_projects(PROJECTS_DIR, self._query)
            self.results_ready.emit(results)
        except Exception as exc:
            _log.warning("search worker error: %s", exc)
            self.error.emit(str(exc))


class CrossProjectSearchPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pm = None
        self._worker: _SearchWorker | None = None
        self._build_ui()

    def set_project_manager(self, pm) -> None:
        self._pm = pm

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Search bar row
        bar = QHBoxLayout()
        self._query_input = QLineEdit()
        self._query_input.setPlaceholderText("Search objects…")
        self._query_input.returnPressed.connect(self._on_search)

        self._scope_combo = QComboBox()
        self._scope_combo.addItem("Current Project", "current")
        self._scope_combo.addItem("All Projects", "all")
        self._scope_combo.setFixedWidth(130)

        self._search_btn = QPushButton("Search")
        self._search_btn.setFixedWidth(70)
        self._search_btn.clicked.connect(self._on_search)

        bar.addWidget(self._query_input)
        bar.addWidget(self._scope_combo)
        bar.addWidget(self._search_btn)
        layout.addLayout(bar)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(self._status_label)

        # Results table
        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_PROJECT, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_NAME,    QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_TYPE,    QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_STATUS,  QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_SNIPPET, QHeaderView.ResizeMode.Stretch)

        mono = QFont("Monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self._table.setFont(mono)
        self._table.setStyleSheet(
            "QTableWidget { background: #1e1e1e; gridline-color: #333; }"
            "QTableWidget::item { color: #cccccc; padding: 2px 4px; }"
            "QTableWidget::item:selected { background: #3d3d3d; }"
        )
        layout.addWidget(self._table, stretch=1)

    # ------------------------------------------------------------------
    # Search logic
    # ------------------------------------------------------------------

    def _on_search(self) -> None:
        query = self._query_input.text().strip()
        if not query:
            return
        if self._worker and self._worker.isRunning():
            return

        scope = self._scope_combo.currentData()
        self._search_btn.setEnabled(False)
        self._status_label.setText("Searching…")
        self._table.setRowCount(0)

        self._worker = _SearchWorker(scope, query, self._pm)
        self._worker.results_ready.connect(self._on_results)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(lambda: self._search_btn.setEnabled(True))
        self._worker.start()

    def _on_results(self, results: list) -> None:
        self._table.setRowCount(0)
        for row_idx, r in enumerate(results):
            self._table.insertRow(row_idx)
            self._table.setItem(row_idx, _COL_PROJECT, QTableWidgetItem(r.get("project", "")))
            self._table.setItem(row_idx, _COL_NAME,    QTableWidgetItem(r.get("name", "")))
            self._table.setItem(row_idx, _COL_TYPE,    QTableWidgetItem(r.get("type", "")))
            self._table.setItem(row_idx, _COL_STATUS,  QTableWidgetItem(r.get("status", "")))
            self._table.setItem(row_idx, _COL_SNIPPET, QTableWidgetItem(r.get("snippet", "")))
        n = len(results)
        self._status_label.setText(f"{n} result{'s' if n != 1 else ''} found.")

    def _on_error(self, msg: str) -> None:
        self._status_label.setText(f"Search error: {msg}")
