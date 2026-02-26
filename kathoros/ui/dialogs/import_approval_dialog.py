"""
ImportApprovalDialog — shows parsed object suggestions for researcher approval.
Researcher can approve, edit, or reject each suggested object.
Approved objects returned for DB write. No DB calls here.
"""
import logging

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

_log = logging.getLogger("kathoros.ui.dialogs.import_approval_dialog")

_TYPES = ["concept", "definition", "derivation", "prediction", "evidence", "question"]


class _ObjectRow(QWidget):
    def __init__(self, obj: dict, parent=None) -> None:
        super().__init__(parent)
        self._approved = True
        self._orig = obj   # keep all fields for pass-through on get_result()

        # Approve checkbox
        self._check = QCheckBox()
        self._check.setChecked(True)
        self._check.toggled.connect(self._on_toggle)

        # Name
        self._name = QLineEdit(obj.get("name", ""))
        self._name.setStyleSheet(
            "QLineEdit { background: #2d2d2d; color: #cccccc; border: 1px solid #333; padding: 3px; }"
        )

        # Type
        self._type = QComboBox()
        self._type.addItems(_TYPES)
        t = obj.get("type", "concept")
        if t in _TYPES:
            self._type.setCurrentText(t)
        self._type.setFixedWidth(110)

        # Tags
        self._tags = QLineEdit(", ".join(obj.get("tags", [])))
        self._tags.setPlaceholderText("tags, comma separated")
        self._tags.setStyleSheet(
            "QLineEdit { background: #2d2d2d; color: #888888; border: 1px solid #333; padding: 3px; }"
        )

        # Description
        self._desc = QPlainTextEdit(obj.get("description", ""))
        self._desc.setFixedHeight(60)
        self._desc.setStyleSheet(
            "QPlainTextEdit { background: #2d2d2d; color: #cccccc; border: 1px solid #333; padding: 3px; }"
        )

        # Source label
        src = obj.get("source_file", "")
        src_label = QLabel(f"📄 {src}")
        src_label.setStyleSheet("color: #666666; font-size: 10px;")

        top_row = QHBoxLayout()
        top_row.addWidget(self._check)
        top_row.addWidget(self._name, stretch=2)
        top_row.addWidget(self._type)
        top_row.addWidget(self._tags, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top_row)
        layout.addWidget(self._desc)
        layout.addWidget(src_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333;")
        layout.addWidget(sep)

    def _on_toggle(self, checked: bool) -> None:
        self._approved = checked
        opacity = "1.0" if checked else "0.4"
        self._name.setEnabled(checked)
        self._type.setEnabled(checked)
        self._tags.setEnabled(checked)
        self._desc.setEnabled(checked)

    def get_result(self) -> dict | None:
        if not self._approved:
            return None
        # Start with all original fields (preserves source_file, math_expression,
        # latex, researcher_notes, depends_on, etc.) then overlay editable UI fields.
        result = dict(self._orig)
        result["name"] = self._name.text().strip()
        result["type"] = self._type.currentText()
        result["description"] = self._desc.toPlainText().strip()
        result["tags"] = [t.strip() for t in self._tags.text().split(",") if t.strip()]
        return result


class ImportApprovalDialog(QDialog):
    def __init__(self, suggestions: list[dict], parent=None) -> None:
        super().__init__(parent)
        self._results: list[dict] = []
        self.setWindowTitle(f"Import — {len(suggestions)} suggested objects")
        self.setMinimumSize(640, 500)
        self.setModal(True)
        self.setStyleSheet("QDialog { background: #1e1e1e; color: #cccccc; }")

        header = QLabel(f"Review {len(suggestions)} suggested research objects:")
        header.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px;")

        # Scrollable list of object rows
        self._rows: list[_ObjectRow] = []
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 4, 4, 4)

        for obj in suggestions:
            row = _ObjectRow(obj)
            self._rows.append(row)
            scroll_layout.addWidget(row)
        scroll_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(scroll_content)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #1e1e1e; }")

        # Buttons
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(lambda: [r._check.setChecked(True) for r in self._rows])
        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(lambda: [r._check.setChecked(False) for r in self._rows])

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        import_btn = QPushButton("Import Selected")
        import_btn.setStyleSheet(
            "QPushButton { background: #4090f0; color: white; padding: 6px 16px; }"
            "QPushButton:hover { background: #50a0ff; }"
        )
        import_btn.clicked.connect(self._on_import)
        import_btn.setDefault(True)

        btn_row = QHBoxLayout()
        btn_row.addWidget(select_all_btn)
        btn_row.addWidget(select_none_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(import_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(header)
        layout.addWidget(scroll, stretch=1)
        layout.addLayout(btn_row)

    def _on_import(self) -> None:
        self._results = [r for row in self._rows if (r := row.get_result())]
        _log.info("import approved: %d objects", len(self._results))
        self.accept()

    @property
    def results(self) -> list[dict]:
        return self._results
