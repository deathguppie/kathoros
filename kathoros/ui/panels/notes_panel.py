"""
NotesPanel — per-project researcher notepad.
Split list (left) + editor (right). Notes persist across sessions.
No DB access here — all persistence via signals to main_window handlers.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

_log = logging.getLogger("kathoros.ui.panels.notes_panel")

_FORMAT_OPTIONS = [
    ("Markdown", "markdown"),
    ("LaTeX",    "latex"),
    ("Plain Text", "text"),
]


class NotesPanel(QWidget):
    note_create_requested = pyqtSignal()
    note_delete_requested = pyqtSignal(list)               # list[int] note ids
    note_save_requested   = pyqtSignal(int, str, str, str) # id, title, content, format
    note_selected         = pyqtSignal(int)                 # note id to load

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_note_id: int | None = None
        self._suppressing: bool = False  # prevent save-on-load feedback loop
        self._build_ui()
        self._wire()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: list + toolbar ──────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(4)

        toolbar = QHBoxLayout()
        self._btn_new = QPushButton("New")
        self._btn_new.setFixedHeight(26)
        self._btn_delete = QPushButton("Delete")
        self._btn_delete.setFixedHeight(26)
        toolbar.addWidget(self._btn_new)
        toolbar.addWidget(self._btn_delete)
        toolbar.addStretch()
        left_layout.addLayout(toolbar)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        left_layout.addWidget(self._list)

        # ── Right: header + editor ────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(4)

        header = QHBoxLayout()
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Title")
        self._fmt_combo = QComboBox()
        for label, _ in _FORMAT_OPTIONS:
            self._fmt_combo.addItem(label)
        self._fmt_combo.setFixedWidth(110)
        header.addWidget(self._title_edit, stretch=1)
        header.addWidget(QLabel("Format:"))
        header.addWidget(self._fmt_combo)
        right_layout.addLayout(header)

        self._editor = QPlainTextEdit()
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self._editor.setFont(mono)
        self._editor.setStyleSheet(
            "QPlainTextEdit { background: #1e1e1e; color: #d4d4d4; border: none; }"
        )
        right_layout.addWidget(self._editor)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)
        root.addWidget(splitter)

    def _wire(self) -> None:
        self._btn_new.clicked.connect(self._on_new_clicked)
        self._btn_delete.clicked.connect(self._on_delete_clicked)
        self._list.currentRowChanged.connect(self._on_row_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_notes(self, notes: list[dict]) -> None:
        """Repopulate the list, restoring selection by id if possible."""
        prev_id = self._current_note_id
        self._suppressing = True
        self._list.clear()
        for note in notes:
            item = QListWidgetItem(note.get("title") or "Untitled")
            item.setData(Qt.ItemDataRole.UserRole, note["id"])
            self._list.addItem(item)
        # Restore selection
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.ItemDataRole.UserRole) == prev_id:
                self._list.setCurrentRow(i)
                self._suppressing = False
                return
        # Select first if no previous selection matches
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        self._suppressing = False

    def set_current_note(self, note: dict) -> None:
        """Populate the right side with note data (title/content/format)."""
        self._suppressing = True
        self._current_note_id = note["id"]
        self._title_edit.setText(note.get("title") or "")
        self._editor.setPlainText(note.get("content") or "")
        fmt = note.get("format", "markdown")
        for i, (_, val) in enumerate(_FORMAT_OPTIONS):
            if val == fmt:
                self._fmt_combo.setCurrentIndex(i)
                break
        self._suppressing = False
        # Highlight the matching list item
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.ItemDataRole.UserRole) == note["id"]:
                self._list.setCurrentRow(i)
                break

    def selected_note_ids(self) -> list[int]:
        """Return ids of all highlighted rows."""
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self._list.selectedItems()
        ]

    def clear(self) -> None:
        """Reset panel on project switch."""
        self._suppressing = True
        self._list.clear()
        self._current_note_id = None
        self._title_edit.clear()
        self._editor.clear()
        self._fmt_combo.setCurrentIndex(0)
        self._suppressing = False

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_new_clicked(self) -> None:
        self.note_create_requested.emit()

    def _on_delete_clicked(self) -> None:
        ids = self.selected_note_ids()
        if ids:
            self.note_delete_requested.emit(ids)

    def _on_row_changed(self, row: int) -> None:
        if self._suppressing:
            return
        # Auto-save previous note before switching
        if self._current_note_id is not None:
            self._emit_save()
        if row < 0:
            self._current_note_id = None
            self._title_edit.clear()
            self._editor.clear()
            return
        item = self._list.item(row)
        if item is None:
            return
        note_id = item.data(Qt.ItemDataRole.UserRole)
        # Request load via parent — handled by main_window via note_save_requested
        # which reloads the list; we just emit a save and set_current_note is called
        # by _on_note_save → load_notes → selection restoration drives set_current_note.
        # However, we also need to populate the editor immediately from the list item.
        # Since we don't have content here, we signal save of previous and update id.
        self._current_note_id = note_id
        self.note_selected.emit(note_id)

    def _emit_save(self) -> None:
        if self._current_note_id is None:
            return
        self.note_save_requested.emit(
            self._current_note_id,
            self._title_edit.text(),
            self._editor.toPlainText(),
            _FORMAT_OPTIONS[self._fmt_combo.currentIndex()][1],
        )
