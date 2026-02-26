"""
ObjectsPanel — left panel showing staged research objects with pipeline status.
Read-only display. No DB calls. Receives data via load_objects().
UI must not import db.queries directly.

Tree layout: objects with no depends_on are roots; objects that list another
object's ID in depends_on appear as children of that object.
"""
import json
import logging
from PyQt6.QtWidgets import (
    QWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QLabel,
    QPushButton, QHBoxLayout, QMenu, QApplication, QInputDialog,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor

_log = logging.getLogger("kathoros.ui.panels.objects_panel")

# Custom roles
_ROLE_OBJ_ID    = Qt.ItemDataRole.UserRole          # int object id, or None for source items
_ROLE_SRC_PARENT = Qt.ItemDataRole(Qt.ItemDataRole.UserRole.value + 1)  # parent obj id on source items

_STATUS = {
    "pending":      ("●", "#f0c040"),
    "audited":      ("●", "#4090f0"),
    "flagged":      ("●", "#f04040"),
    "disputed":     ("●", "#a040f0"),
    "committed":    ("✓", "#40c040"),
    "open_question":("?", "#f08040"),
}
_TYPE_ABBREV = {
    "concept":       "concept",
    "definition":    "def",
    "derivation":    "deriv",
    "prediction":    "pred",
    "evidence":      "evid",
    "open_question": "q?",
    "data":          "data",
}


class ObjectsPanel(QWidget):
    object_selected = pyqtSignal(int)        # left-click — show in editor
    object_edit_requested = pyqtSignal(int)  # double-click / context menu — open dialog
    status_change_requested = pyqtSignal(int, str)
    tags_change_requested = pyqtSignal(int, list)        # (object_id, new_tags)
    parent_change_requested = pyqtSignal(int, list)      # (object_id, new_depends_on_ids)
    refresh_requested = pyqtSignal()
    audit_requested = pyqtSignal(int)
    open_source_requested = pyqtSignal(int)  # open source file in reader

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._objects: list[dict] = []

        self._header = QLabel("Objects (0)")
        self._header.setStyleSheet("font-weight: bold; padding: 4px;")

        self._tree = QTreeWidget()
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Name", "Status"])
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setSectionResizeMode(
            0, self._tree.header().ResizeMode.Stretch
        )
        self._tree.header().setSectionResizeMode(
            1, self._tree.header().ResizeMode.ResizeToContents
        )
        self._tree.setStyleSheet(
            "QTreeWidget { background: #252525; border: 1px solid #333; }"
            "QTreeWidget::item { min-height: 26px; padding: 2px; }"
            "QTreeWidget::item:selected { background: #3d3d3d; }"
        )
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_double_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_requested)
        self._audit_btn = QPushButton("Audit")
        self._audit_btn.setEnabled(False)
        self._audit_btn.clicked.connect(self._on_audit_clicked)
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(self._audit_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._header)
        layout.addWidget(self._tree)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_objects(self, objects: list[dict]) -> None:
        self._objects = objects
        self._rebuild_tree()
        self._header.setText(f"Objects ({len(objects)})")

    def clear(self) -> None:
        self._objects = []
        self._tree.clear()
        self._header.setText("Objects (0)")

    # ------------------------------------------------------------------
    # Tree construction
    # ------------------------------------------------------------------

    def _rebuild_tree(self) -> None:
        self._tree.clear()

        id_to_item: dict[int, QTreeWidgetItem] = {}

        # Build all object items first
        for obj in self._objects:
            item = self._make_item(obj)
            id_to_item[obj["id"]] = item

        # Place items: child of first valid parent found in depends_on
        placed: set[int] = set()
        for obj in self._objects:
            raw = obj.get("depends_on") or "[]"
            try:
                deps = json.loads(raw) if isinstance(raw, str) else raw
            except (ValueError, TypeError):
                deps = []
            for dep_id in deps:
                if dep_id in id_to_item and dep_id != obj["id"]:
                    id_to_item[dep_id].addChild(id_to_item[obj["id"]])
                    placed.add(obj["id"])
                    break

        # Root-level items
        for obj in self._objects:
            if obj["id"] not in placed:
                self._tree.addTopLevelItem(id_to_item[obj["id"]])

        # Add source-file child branch to every object that has one
        for obj in self._objects:
            src = (obj.get("source_file") or "").strip()
            if not src:
                continue
            basename = src.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            src_item = QTreeWidgetItem([f"  📄  {basename}", ""])
            src_item.setData(0, _ROLE_OBJ_ID, None)
            src_item.setData(0, _ROLE_SRC_PARENT, obj["id"])
            src_item.setForeground(0, QColor("#5a8fa8"))
            src_item.setToolTip(0, src)
            id_to_item[obj["id"]].addChild(src_item)

        self._tree.expandAll()

    def _make_item(self, obj: dict) -> QTreeWidgetItem:
        icon, color = _STATUS.get(obj.get("status", "").lower(), ("?", "#888888"))
        abbrev = _TYPE_ABBREV.get(obj.get("type", ""), obj.get("type", ""))
        name = obj.get("name", "?")
        item = QTreeWidgetItem([f"[{abbrev}]  {name}", icon])
        item.setData(0, _ROLE_OBJ_ID, obj["id"])
        item.setForeground(0, QColor("#cccccc"))
        item.setForeground(1, QColor(color))
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)
        return item

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def _current_id(self) -> int | None:
        items = self._tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, _ROLE_OBJ_ID)

    def _on_selection_changed(self) -> None:
        items = self._tree.selectedItems()
        if not items:
            self._audit_btn.setEnabled(False)
            return
        item = items[0]
        oid = item.data(0, _ROLE_OBJ_ID)
        src_parent = item.data(0, _ROLE_SRC_PARENT)
        if oid is not None:
            self._audit_btn.setEnabled(True)
            self.object_selected.emit(oid)
        elif src_parent is not None:
            self._audit_btn.setEnabled(False)
            self.open_source_requested.emit(src_parent)

    def _on_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        oid = item.data(0, _ROLE_OBJ_ID)
        src_parent = item.data(0, _ROLE_SRC_PARENT)
        if oid is not None:
            self.object_edit_requested.emit(oid)
        elif src_parent is not None:
            self.open_source_requested.emit(src_parent)

    def _on_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if item is None:
            return
        oid = item.data(0, _ROLE_OBJ_ID)
        src_parent = item.data(0, _ROLE_SRC_PARENT)
        menu = QMenu(self)
        if oid is not None:
            menu.addAction("View / Edit...", lambda: self.object_edit_requested.emit(oid))
            menu.addAction("Open Source in Reader", lambda: self.open_source_requested.emit(oid))
            menu.addAction("Audit...", lambda: self.audit_requested.emit(oid))
            menu.addSeparator()
            status_menu = menu.addMenu("Set Status")
            for s in ("pending", "audited", "flagged", "disputed"):
                status_menu.addAction(
                    s.capitalize(),
                    lambda checked=False, st=s: self.status_change_requested.emit(oid, st),
                )
            # --- Edit Tags ---
            menu.addSeparator()
            menu.addAction("Edit Tags...", lambda _oid=oid: self._edit_tags_dialog(_oid))

            # --- Set Parent ---
            parent_menu = menu.addMenu("Set Parent")
            parent_menu.addAction(
                "None (make root)",
                lambda _oid=oid: self.parent_change_requested.emit(_oid, []),
            )
            parent_menu.addSeparator()
            # current depends_on for this object
            cur_obj = next((o for o in self._objects if o["id"] == oid), None)
            cur_deps: list[int] = []
            if cur_obj:
                raw = cur_obj.get("depends_on") or "[]"
                try:
                    cur_deps = json.loads(raw) if isinstance(raw, str) else raw
                except (ValueError, TypeError):
                    cur_deps = []
            for candidate in self._objects:
                if candidate["id"] == oid:
                    continue
                cname = candidate.get("name", f"id={candidate['id']}")
                act = parent_menu.addAction(
                    cname,
                    lambda _oid=oid, _cid=candidate["id"]: self.parent_change_requested.emit(_oid, [_cid]),
                )
                if candidate["id"] in cur_deps:
                    act.setCheckable(True)
                    act.setChecked(True)

            menu.addSeparator()
            name = item.text(0).split("  ", 1)[-1] if "  " in item.text(0) else item.text(0)
            menu.addAction("Copy Name", lambda: QApplication.clipboard().setText(name))
        elif src_parent is not None:
            menu.addAction("Open in Reader", lambda: self.open_source_requested.emit(src_parent))
            tooltip = item.toolTip(0)
            if tooltip:
                menu.addAction("Copy Path", lambda: QApplication.clipboard().setText(tooltip))
        menu.exec(self._tree.mapToGlobal(pos))

    def _edit_tags_dialog(self, oid: int) -> None:
        obj = next((o for o in self._objects if o["id"] == oid), None)
        current_tags: list[str] = []
        if obj:
            raw = obj.get("tags") or "[]"
            try:
                current_tags = json.loads(raw) if isinstance(raw, str) else raw
            except (ValueError, TypeError):
                current_tags = []
        prefill = ", ".join(current_tags)
        text, ok = QInputDialog.getText(self, "Edit Tags", "Tags (comma-separated):", text=prefill)
        if ok:
            new_tags = [t.strip() for t in text.split(",") if t.strip()]
            self.tags_change_requested.emit(oid, new_tags)

    def _on_audit_clicked(self) -> None:
        oid = self._current_id()
        if oid is not None:
            self.audit_requested.emit(oid)
