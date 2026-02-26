"""
EditorPanel — code/text editor with language selector and context toolbars.
Pygments syntax highlighting. No DB calls.
"""
import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from kathoros.ui.panels.syntax_highlighter import PygmentsHighlighter

_log = logging.getLogger("kathoros.ui.panels.editor_panel")

_LANGUAGES = ["python", "markdown", "text"]
_LANG_DISPLAY = ["Python", "Markdown", "Text"]


def _make_toolbar(*widgets) -> QWidget:
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(2, 2, 2, 2)
    for item in widgets:
        if item == "|":
            sep = QLabel("|")
            sep.setStyleSheet("color: #444;")
            layout.addWidget(sep)
        elif isinstance(item, str):
            btn = QPushButton(item)
            if len(item) == 1:
                btn.setFixedWidth(28)
            layout.addWidget(btn)
        else:
            layout.addWidget(item)
    layout.addStretch()
    return w


class EditorPanel(QWidget):
    content_changed = pyqtSignal()
    save_requested = pyqtSignal(str)
    language_changed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._filename = ""
        self._find_visible = False

        # Language selector
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(_LANG_DISPLAY)
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)

        # Toolbar stack — one QWidget per language
        self._toolbar_stack = QStackedWidget()
        self._toolbar_stack.setMaximumHeight(36)

        # Python toolbar
        self._py_run_btn = QPushButton("Run")
        self._py_run_btn.clicked.connect(self._on_python_run)
        self._py_fmt_btn = QPushButton("Format")
        py_w = QWidget()
        py_l = QHBoxLayout(py_w)
        py_l.setContentsMargins(2, 2, 2, 2)
        py_l.addWidget(self._py_run_btn)
        py_l.addWidget(self._py_fmt_btn)
        py_l.addStretch()
        self._toolbar_stack.addWidget(py_w)

        # Markdown toolbar
        md_w = QWidget()
        md_l = QHBoxLayout(md_w)
        md_l.setContentsMargins(2, 2, 2, 2)
        for label, insert in [("Bold", "**text**"), ("Italic", "_text_"),
                               ("H1", "# "), ("H2", "## ")]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, s=insert: self._insert_at_cursor(s))
            md_l.addWidget(btn)
        wc_btn = QPushButton("Word Count")
        wc_btn.clicked.connect(self._on_word_count)
        md_l.addWidget(wc_btn)
        md_l.addStretch()
        self._toolbar_stack.addWidget(md_w)

        # Text toolbar
        tx_w = QWidget()
        tx_l = QHBoxLayout(tx_w)
        tx_l.setContentsMargins(2, 2, 2, 2)
        wc2_btn = QPushButton("Word Count")
        wc2_btn.clicked.connect(self._on_word_count)
        find_btn = QPushButton("Find")
        find_btn.clicked.connect(self._toggle_find)
        tx_l.addWidget(wc2_btn)
        tx_l.addWidget(find_btn)
        tx_l.addStretch()
        self._toolbar_stack.addWidget(tx_w)

        # Editor
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)
        self._editor = QPlainTextEdit()
        self._editor.setFont(font)
        self._editor.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #cccccc; border: 1px solid #333; }"
        )
        self._editor.cursorPositionChanged.connect(self._on_cursor_moved)
        self._editor.textChanged.connect(self.content_changed)
        self._highlighter = PygmentsHighlighter(self._editor.document(), "text")

        # Find bar (hidden by default)
        self._find_bar = QLineEdit()
        self._find_bar.setPlaceholderText("Find... (Enter to search)")
        self._find_bar.setStyleSheet(
            "QLineEdit { background: #2d2d2d; color: #cccccc; border: 1px solid #555; padding: 2px; }"
        )
        self._find_bar.returnPressed.connect(self._do_find)
        self._find_bar.setVisible(False)

        # Status bar
        self._line_col = QLabel("1:1")
        self._char_count = QLabel("0 chars")
        self._filename_label = QLabel("No file open")
        self._filename_label.setStyleSheet("color: #888888;")
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(lambda: self.save_requested.emit(self.get_content()))

        status = QHBoxLayout()
        status.addWidget(self._line_col)
        status.addWidget(self._char_count)
        status.addStretch()
        status.addWidget(self._filename_label)
        status.addWidget(save_btn)

        # Top bar
        top = QHBoxLayout()
        top.addWidget(QLabel("Language:"))
        top.addWidget(self._lang_combo)
        top.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top)
        layout.addWidget(self._toolbar_stack)
        layout.addWidget(self._editor)
        layout.addWidget(self._find_bar)
        layout.addLayout(status)

    def load_object(self, obj: dict) -> None:
        """Display a research object's content in the editor (read-friendly markdown)."""
        import json
        parts = []
        name   = obj.get("name") or "Untitled"
        otype  = obj.get("type") or ""
        status = obj.get("status") or ""
        parts.append(f"# {name}  [{otype}]")
        parts.append(f"**Status:** {status}")
        parts.append("")

        content = (obj.get("content") or "").strip()
        if content:
            parts.append(content)
            parts.append("")

        math = (obj.get("math_expression") or "").strip()
        if math:
            parts.append("## Math Expression")
            parts.append(f"```\n{math}\n```")
            parts.append("")

        latex = (obj.get("latex") or "").strip()
        if latex:
            parts.append("## LaTeX")
            parts.append(f"```latex\n{latex}\n```")
            parts.append("")

        notes = (obj.get("researcher_notes") or "").strip()
        if notes:
            parts.append("## Researcher Notes")
            parts.append(notes)
            parts.append("")

        raw_tags = obj.get("tags") or "[]"
        try:
            tags = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
        except (ValueError, TypeError):
            tags = []
        if tags:
            parts.append(f"**Tags:** {', '.join(str(t) for t in tags)}")

        self.load_content("\n".join(parts), filename=f"{name}.md")

    def load_content(self, content: str, filename: str = "") -> None:
        self._filename = filename
        self._editor.setPlainText(content)
        self._filename_label.setText(filename or "No file open")
        lang = self._detect_language(filename)
        self.set_language(lang)

    def get_content(self) -> str:
        return self._editor.toPlainText()

    def set_language(self, language: str) -> None:
        language = language.lower()
        if language not in _LANGUAGES:
            language = "text"
        idx = _LANGUAGES.index(language)
        self._lang_combo.setCurrentIndex(idx)
        self._toolbar_stack.setCurrentIndex(idx)
        self._highlighter.set_language(language)
        self.language_changed.emit(language)

    def _detect_language(self, filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return {"py": "python", "md": "markdown"}.get(ext, "text")

    def _on_language_changed(self, index: int) -> None:
        lang = _LANGUAGES[index]
        self._toolbar_stack.setCurrentIndex(index)
        self._highlighter.set_language(lang)
        self.language_changed.emit(lang)

    def _on_python_run(self) -> None:
        self.save_requested.emit(self.get_content())

    def _insert_at_cursor(self, text: str) -> None:
        self._editor.textCursor().insertText(text)

    def _on_word_count(self) -> None:
        content = self.get_content()
        words = len(content.split())
        chars = len(content)
        self._char_count.setText(f"{chars} chars, {words} words")

    def _toggle_find(self) -> None:
        self._find_visible = not self._find_visible
        self._find_bar.setVisible(self._find_visible)
        if self._find_visible:
            self._find_bar.setFocus()

    def _do_find(self) -> None:
        text = self._find_bar.text()
        if text:
            found = self._editor.find(text)
            if not found:
                self._editor.moveCursor(QTextCursor.MoveOperation.Start)
                self._editor.find(text)

    def _on_cursor_moved(self) -> None:
        cursor = self._editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.positionInBlock() + 1
        content = self.get_content()
        self._line_col.setText(f"{line}:{col}")
        self._char_count.setText(f"{len(content)} chars")
