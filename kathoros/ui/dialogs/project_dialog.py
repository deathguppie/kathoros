"""
ProjectDialog — shown on startup (and via File > Switch Project) to open or create a project.
Returns project info to main window via accepted signal.
No DB access here — delegates to ProjectManager.
"""
from __future__ import annotations
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QTableWidget, QTableWidgetItem,
    QCheckBox, QHeaderView, QAbstractItemView, QWidget
)
from PyQt6.QtCore import Qt

_log = logging.getLogger("kathoros.ui.dialogs.project_dialog")

_COL_NAME, _COL_DESCRIPTION, _COL_OBJECTS, _COL_SESSIONS, _COL_LAST_ACTIVE, _COL_STATUS = range(6)


class ProjectDialog(QDialog):
    """
    Open/create/archive/delete projects.
    Caller checks .result() == Accepted and reads .selected_project after exec().
    """

    def __init__(self, project_manager, parent=None) -> None:
        super().__init__(parent)
        self._pm = project_manager
        self._show_archived = False
        self.selected_project: dict | None = None
        self.setWindowTitle("Kathoros — Open Project")
        self.setMinimumSize(720, 480)
        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Select a project or create a new one")
        title.setStyleSheet("font-size: 14px; padding: 8px;")
        layout.addWidget(title)

        # Project table
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Name", "Description", "Objects", "Sessions", "Last Active", "Status"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_DESCRIPTION, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_OBJECTS, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_SESSIONS, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_LAST_ACTIVE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemDoubleClicked.connect(self._open_selected)
        layout.addWidget(self._table)

        # Show archived toggle
        self._archived_check = QCheckBox("Show archived projects")
        self._archived_check.stateChanged.connect(self._on_archived_toggled)
        layout.addWidget(self._archived_check)

        # Create row
        create_widget = QWidget()
        create_layout = QHBoxLayout(create_widget)
        create_layout.setContentsMargins(0, 0, 0, 0)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("New project name...")
        self._name_input.returnPressed.connect(self._create_project)
        create_layout.addWidget(self._name_input, 2)
        self._desc_input = QLineEdit()
        self._desc_input.setPlaceholderText("Description (optional)...")
        create_layout.addWidget(self._desc_input, 3)
        create_btn = QPushButton("Create")
        create_btn.clicked.connect(self._create_project)
        create_layout.addWidget(create_btn)
        layout.addWidget(create_widget)

        # Action buttons
        btn_layout = QHBoxLayout()
        open_btn = QPushButton("Open Selected")
        open_btn.clicked.connect(self._open_selected)
        archive_btn = QPushButton("Archive")
        archive_btn.clicked.connect(self._archive_selected)
        delete_btn = QPushButton("Delete...")
        delete_btn.setStyleSheet("color: red;")
        delete_btn.clicked.connect(self._delete_selected)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(open_btn)
        btn_layout.addWidget(archive_btn)
        btn_layout.addWidget(delete_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _refresh_list(self) -> None:
        self._table.setRowCount(0)
        for p in self._pm.list_projects(include_archived=self._show_archived):
            row = self._table.rowCount()
            self._table.insertRow(row)

            name_item = QTableWidgetItem(p["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, p)
            self._table.setItem(row, _COL_NAME, name_item)
            self._table.setItem(row, _COL_DESCRIPTION, QTableWidgetItem(p["description"]))
            self._table.setItem(row, _COL_OBJECTS, QTableWidgetItem(str(p["object_count"])))
            self._table.setItem(row, _COL_SESSIONS, QTableWidgetItem(str(p["session_count"])))
            last = p["last_active"][:10] if p["last_active"] else ""
            self._table.setItem(row, _COL_LAST_ACTIVE, QTableWidgetItem(last))
            self._table.setItem(row, _COL_STATUS, QTableWidgetItem(p["status"]))

    def _selected_project_data(self) -> dict | None:
        row = self._table.currentRow()
        item = self._table.item(row, _COL_NAME)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_archived_toggled(self, state: int) -> None:
        self._show_archived = (state == Qt.CheckState.Checked.value)
        self._refresh_list()

    def _open_selected(self) -> None:
        p = self._selected_project_data()
        if p is None:
            QMessageBox.warning(self, "No Selection", "Select a project first.")
            return
        try:
            result = self._pm.open_project(p["name"])
            self.selected_project = result
            self.accept()
        except Exception as exc:
            _log.error("failed to open project: %s", exc)
            QMessageBox.critical(self, "Error", str(exc))

    def _create_project(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Project name cannot be empty.")
            return
        description = self._desc_input.text().strip()
        try:
            result = self._pm.create_project(name, description=description)
            self.selected_project = result
            self.accept()
        except FileExistsError:
            QMessageBox.warning(self, "Exists", f"Project '{name}' already exists.")
        except Exception as exc:
            _log.error("failed to create project: %s", exc)
            QMessageBox.critical(self, "Error", str(exc))

    def _archive_selected(self) -> None:
        p = self._selected_project_data()
        if p is None:
            QMessageBox.warning(self, "No Selection", "Select a project first.")
            return
        if p["status"] == "archived":
            QMessageBox.information(self, "Already Archived",
                                    f"'{p['name']}' is already archived.")
            return
        answer = QMessageBox.question(
            self, "Archive Project",
            f"Archive '{p['name']}'?\n\nAll data is preserved; the project will be hidden "
            "unless 'Show archived projects' is checked.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._pm.archive_project(p["name"])
            self._refresh_list()
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot Archive", str(exc))
        except Exception as exc:
            _log.error("failed to archive project: %s", exc)
            QMessageBox.critical(self, "Error", str(exc))

    def _delete_selected(self) -> None:
        p = self._selected_project_data()
        if p is None:
            QMessageBox.warning(self, "No Selection", "Select a project first.")
            return
        answer = QMessageBox.warning(
            self, "Delete Project",
            f"Permanently delete '{p['name']}'?\n\n"
            "This cannot be undone. All objects, sessions, and files will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._pm.delete_project(p["name"])
            self._refresh_list()
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot Delete", str(exc))
        except Exception as exc:
            _log.error("failed to delete project: %s", exc)
            QMessageBox.critical(self, "Error", str(exc))
