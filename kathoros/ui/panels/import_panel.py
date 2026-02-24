"""
ImportPanel — lists supported files in project docs/ for agent import.
Researcher selects files, clicks Import Selected.
Emits import_requested(list[str]) with selected paths.
No DB calls. Read-only file listing.
"""
import logging
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton
)
from PyQt6.QtCore import pyqtSignal, Qt

_log = logging.getLogger("kathoros.ui.panels.import_panel")

_SUPPORTED = {".md": "📄", ".py": "🐍", ".tex": "🔬", ".json": "📦"}


def _fmt_size(b: int) -> str:
    if b < 1024:
        return f"{b}B"
    if b < 1024 * 1024:
        return f"{b//1024}KB"
    return f"{b//(1024*1024)}MB"


class ImportPanel(QWidget):
    import_requested = pyqtSignal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._docs_path: Path | None = None

        # Top toolbar
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        self._path_label = QLabel("No project open")
        self._path_label.setStyleSheet("color: #888888; padding: 0 8px;")

        top = QHBoxLayout()
        top.addWidget(refresh_btn)
        top.addWidget(self._path_label)
        top.addStretch()

        # File list
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background: #1a1a1a; color: #cccccc; border: 1px solid #333; }"
            "QListWidget::item { padding: 4px; }"
            "QListWidget::item:hover { background: #2d2d2d; }"
        )

        # Bottom toolbar
        sel_all_btn = QPushButton("Select All")
        sel_all_btn.clicked.connect(self._select_all)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_selection)
        self._count_label = QLabel("0 files")
        self._count_label.setStyleSheet("color: #888888; padding: 0 8px;")
        import_btn = QPushButton("Import Selected")
        import_btn.setStyleSheet(
            "QPushButton { background: #4090f0; color: white; padding: 4px 12px; }"
            "QPushButton:hover { background: #50a0ff; }"
            "QPushButton:disabled { background: #333; color: #666; }"
        )
        import_btn.clicked.connect(self._on_import_clicked)

        bottom = QHBoxLayout()
        bottom.addWidget(sel_all_btn)
        bottom.addWidget(clear_btn)
        bottom.addStretch()
        bottom.addWidget(self._count_label)
        bottom.addWidget(import_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top)
        layout.addWidget(self._list)
        layout.addLayout(bottom)

    def set_docs_path(self, path: str) -> None:
        self._docs_path = Path(path)
        self._path_label.setText(str(self._docs_path))
        self.refresh()

    def refresh(self) -> None:
        self._list.clear()
        if not self._docs_path or not self._docs_path.is_dir():
            self._count_label.setText("0 files")
            return
        files = sorted(
            f for f in self._docs_path.rglob("*")
            if f.is_file() and f.suffix.lower() in _SUPPORTED
        )
        for f in files:
            icon = _SUPPORTED.get(f.suffix.lower(), "📄")
            size = _fmt_size(f.stat().st_size)
            rel = f.relative_to(self._docs_path)
            item = QListWidgetItem(f"{icon}  {rel}  —  {size}")
            item.setData(Qt.ItemDataRole.UserRole, str(f))
            item.setCheckState(Qt.CheckState.Unchecked)
            self._list.addItem(item)
        self._count_label.setText(f"{len(files)} files")

    def get_selected_paths(self) -> list[str]:
        result = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    def _select_all(self) -> None:
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Checked)

    def _clear_selection(self) -> None:
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _on_import_clicked(self) -> None:
        paths = self.get_selected_paths()
        if not paths:
            return
        _log.info("import requested: %d files", len(paths))
        self.import_requested.emit(paths)
