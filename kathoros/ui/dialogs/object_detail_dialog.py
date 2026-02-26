"""
ObjectDetailDialog — detail/edit view for a single research object.
Left-click from ObjectsPanel opens this dialog.
No direct DB access: all writes go through SessionService.
"""
from __future__ import annotations

import json
import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

_log = logging.getLogger("kathoros.ui.dialogs.object_detail_dialog")

_OBJECT_TYPES = [
    "concept", "definition", "derivation",
    "prediction", "evidence", "open_question", "data",
]

_STATUS_COLORS = {
    "pending":   "#f0c040",
    "audited":   "#4090f0",
    "flagged":   "#f04040",
    "disputed":  "#a040f0",
    "committed": "#40c040",
}

_BASE_STYLE = """
QDialog        { background: #1e1e1e; color: #cccccc; }
QTabWidget::pane { border: 1px solid #333; background: #1e1e1e; }
QTabBar::tab   { background: #2d2d2d; color: #999; padding: 6px 14px; }
QTabBar::tab:selected { background: #3d3d3d; color: #cccccc; }
QLabel         { color: #cccccc; }
QLineEdit      { background: #2d2d2d; color: #cccccc; border: 1px solid #444;
                 padding: 3px; border-radius: 3px; }
QComboBox      { background: #2d2d2d; color: #cccccc; border: 1px solid #444;
                 padding: 3px; border-radius: 3px; }
QComboBox QAbstractItemView { background: #2d2d2d; color: #cccccc; }
QPlainTextEdit { background: #2d2d2d; color: #cccccc; border: 1px solid #444;
                 border-radius: 3px; }
QPushButton    { background: #2d2d2d; color: #cccccc; border: 1px solid #555;
                 padding: 4px 12px; border-radius: 3px; }
QPushButton:hover  { background: #3d3d3d; }
QPushButton:pressed { background: #444; }
"""


class ObjectDetailDialog(QDialog):
    open_in_reader = pyqtSignal(str)   # emitted with resolved file path

    def __init__(
        self,
        object_data: dict,
        session_service,
        all_objects: list | None = None,
        docs_path: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._data = object_data
        self._session_service = session_service
        self._docs_path = docs_path
        # Build lookup maps for depends_on name↔id resolution
        _objs = all_objects or []
        self._id_to_name: dict[int, str] = {o["id"]: o["name"] for o in _objs}
        self._name_to_id: dict[str, int] = {o["name"]: o["id"] for o in _objs}

        self.setWindowTitle("Object Detail")
        self.setMinimumSize(700, 550)
        self.setModal(True)
        self.setStyleSheet(_BASE_STYLE)

        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        root.addWidget(self._build_header())

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_info_tab(), "Info")
        self._tabs.addTab(self._build_content_tab(), "Content")
        self._tabs.addTab(self._build_epistemic_tab(), "Epistemic")
        root.addWidget(self._tabs)

        root.addLayout(self._build_button_row())

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: #252525; border-radius: 4px;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        status = self._data.get("status", "pending")
        color = _STATUS_COLORS.get(status.lower(), "#888888")
        name = self._data.get("name", "?")
        obj_type = self._data.get("type", "")

        title_row = QHBoxLayout()
        type_badge = QLabel(f"● {obj_type}")
        type_badge.setStyleSheet(f"color: {color}; font-size: 13px;")
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #e0e0e0;")
        title_row.addWidget(type_badge)
        title_row.addWidget(name_lbl, 1)
        layout.addLayout(title_row)

        meta_parts = [
            f"Status: <span style='color:{color}'>{status}</span>",
            f"ID: {self._data.get('id', '?')}",
            f"v{self._data.get('version', 1)}",
            str(self._data.get("created_at", ""))[:10],
        ]
        meta_lbl = QLabel("  ·  ".join(meta_parts))
        meta_lbl.setStyleSheet("color: #888; font-size: 11px;")
        meta_lbl.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(meta_lbl)

        return w

    # ------------------------------------------------------------------
    # Info tab
    # ------------------------------------------------------------------

    def _build_info_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._name_edit = QLineEdit(self._data.get("name", ""))
        form.addRow("Name:", self._name_edit)

        self._type_combo = QComboBox()
        self._type_combo.addItems(_OBJECT_TYPES)
        current_type = self._data.get("type", "concept")
        if current_type in _OBJECT_TYPES:
            self._type_combo.setCurrentIndex(_OBJECT_TYPES.index(current_type))
        form.addRow("Type:", self._type_combo)

        tags_raw = self._data.get("tags", "[]")
        if isinstance(tags_raw, str):
            try:
                tags_list = json.loads(tags_raw)
            except (json.JSONDecodeError, ValueError):
                tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
        else:
            tags_list = list(tags_raw)
        self._tags_edit = QLineEdit(", ".join(str(t) for t in tags_list))
        form.addRow("Tags:", self._tags_edit)

        source_row = QHBoxLayout()
        self._source_edit = QLineEdit(self._data.get("source_file", "") or "")
        self._source_edit.setPlaceholderText("filename, DOI, arXiv ID, or citation…")
        open_source_btn = QPushButton("Open in Reader")
        open_source_btn.setFixedWidth(110)
        open_source_btn.clicked.connect(self._on_open_source)
        source_row.addWidget(self._source_edit)
        source_row.addWidget(open_source_btn)
        source_widget = QWidget()
        source_widget.setLayout(source_row)
        form.addRow("Source:", source_widget)

        # Depends On — editable as comma-separated object names
        raw_deps = self._data.get("depends_on", "[]")
        if isinstance(raw_deps, str):
            try:
                dep_ids = json.loads(raw_deps)
            except (json.JSONDecodeError, ValueError):
                dep_ids = []
        else:
            dep_ids = list(raw_deps) if raw_deps else []
        dep_names = [self._id_to_name.get(int(d), str(d)) for d in dep_ids if d is not None]
        self._depends_edit = QLineEdit(", ".join(dep_names))
        self._depends_edit.setPlaceholderText("Object names this depends on, comma-separated…")
        form.addRow("Depends On:", self._depends_edit)

        self._notes_edit = QPlainTextEdit(self._data.get("researcher_notes", "") or "")
        self._notes_edit.setFixedHeight(90)
        form.addRow("Notes:", self._notes_edit)

        return w

    # ------------------------------------------------------------------
    # Content tab
    # ------------------------------------------------------------------

    def _build_content_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._content_edit = QPlainTextEdit(self._data.get("content", "") or "")
        self._content_edit.setFixedHeight(160)
        form.addRow("Content:", self._content_edit)

        mono = QFont("Monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)

        self._math_edit = QPlainTextEdit(self._data.get("math_expression", "") or "")
        self._math_edit.setFixedHeight(90)
        self._math_edit.setFont(mono)
        form.addRow("Math:", self._math_edit)

        self._latex_edit = QPlainTextEdit(self._data.get("latex", "") or "")
        self._latex_edit.setFixedHeight(90)
        self._latex_edit.setFont(mono)
        form.addRow("LaTeX:", self._latex_edit)

        return w

    # ------------------------------------------------------------------
    # Epistemic tab (read-only)
    # ------------------------------------------------------------------

    def _build_epistemic_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def ro(key: str, default: str = "—") -> QLabel:
            val = self._data.get(key)
            lbl = QLabel(str(val) if val is not None else default)
            lbl.setStyleSheet("color: #aaa;")
            lbl.setWordWrap(True)
            return lbl

        def ids_label(key: str) -> QLabel:
            raw = self._data.get(key, "[]")
            if isinstance(raw, str):
                try:
                    ids = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    ids = [raw] if raw else []
            else:
                ids = list(raw) if raw else []
            text = ", ".join(str(i) for i in ids) if ids else "—"
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #aaa;")
            lbl.setWordWrap(True)
            return lbl

        form.addRow("Object Type:", ro("object_type"))
        form.addRow("Epistemic Status:", ro("epistemic_status"))
        form.addRow("Claim Level:", ro("claim_level"))
        form.addRow("Narrative Label:", ro("narrative_label"))
        form.addRow("Falsifiable:", ro("falsifiable"))
        form.addRow("Validation Scope:", ro("validation_scope"))
        form.addRow(QLabel(""))
        form.addRow("Depends On:", ids_label("depends_on"))
        form.addRow("Contradicts:", ids_label("contradicts"))
        form.addRow("Related:", ids_label("related_objects"))

        return w

    # ------------------------------------------------------------------
    # Button row
    # ------------------------------------------------------------------

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)

        row.addWidget(cancel_btn)
        row.addWidget(save_btn)
        return row

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_open_source(self) -> None:
        from pathlib import Path
        raw = self._source_edit.text().strip()
        if not raw:
            QMessageBox.information(self, "No Source", "No source file is set for this object.")
            return
        candidate = Path(raw)
        # Try as absolute path first
        if candidate.is_absolute() and candidate.exists():
            self.open_in_reader.emit(str(candidate))
            return
        # Try relative to docs/ directory
        if self._docs_path:
            rel = Path(self._docs_path) / raw
            if rel.exists():
                self.open_in_reader.emit(str(rel))
                return
        # Not found as a local file — may be DOI/arXiv ID etc.
        QMessageBox.information(
            self, "File Not Found",
            f"Could not locate '{raw}' as a local file.\n\n"
            "If this is a DOI or arXiv ID, search for it manually in your browser.",
        )

    def _save(self) -> None:
        object_id = self._data.get("id")
        if object_id is None:
            _log.error("object_id missing from data — cannot save")
            self.reject()
            return

        tags_text = self._tags_edit.text()
        tags_list = [t.strip() for t in tags_text.split(",") if t.strip()]

        # Resolve depends_on names → ids; unknown names are dropped
        dep_names_raw = [n.strip() for n in self._depends_edit.text().split(",") if n.strip()]
        dep_ids = [self._name_to_id[n] for n in dep_names_raw if n in self._name_to_id]

        try:
            self._session_service.update_object(
                object_id,
                name=self._name_edit.text().strip(),
                type=self._type_combo.currentText(),
                content=self._content_edit.toPlainText(),
                math_expression=self._math_edit.toPlainText(),
                latex=self._latex_edit.toPlainText(),
                tags=tags_list,
                researcher_notes=self._notes_edit.toPlainText(),
                source_file=self._source_edit.text().strip(),
                depends_on=dep_ids,
            )
        except Exception as exc:
            _log.error("update_object failed: %s", exc)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Save Failed", str(exc))
            return

        self.accept()
