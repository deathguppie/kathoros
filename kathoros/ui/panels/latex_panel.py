"""
LaTeXPanel — LaTeX editor with pdflatex compilation and PDF preview.
Left: editor. Right: rendered PDF page.
No DB calls.
"""
import logging
import subprocess
import tempfile
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPlainTextEdit, QLabel, QPushButton, QScrollArea
)
from PyQt6.QtCore import pyqtSignal, QThread, Qt
from PyQt6.QtGui import QFont, QPixmap, QImage
from kathoros.ui.panels.syntax_highlighter import PygmentsHighlighter

_log = logging.getLogger("kathoros.ui.panels.latex_panel")

_DEFAULT_TEX = r"""\documentclass{article}
\begin{document}

\title{My Document}
\author{Author}
\maketitle

\section{Introduction}
Hello, world!

\end{document}
"""


class _CompileWorker(QThread):
    finished = pyqtSignal(str, bool)  # (pdf_path_or_error, success)

    def __init__(self, source: str) -> None:
        super().__init__()
        self._source = source

    def run(self) -> None:
        tmp_dir = tempfile.mkdtemp()
        tex_path = os.path.join(tmp_dir, "doc.tex")
        pdf_path = os.path.join(tmp_dir, "doc.pdf")
        try:
            with open(tex_path, "w") as f:
                f.write(self._source)
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode",
                 f"-output-directory={tmp_dir}", tex_path],
                capture_output=True, text=True, timeout=30,
            )
            if os.path.exists(pdf_path):
                self.finished.emit(pdf_path, True)
            else:
                self.finished.emit(result.stdout + result.stderr, False)
        except subprocess.TimeoutExpired:
            self.finished.emit("Compile timed out (30s)", False)
        except Exception as exc:
            self.finished.emit(str(exc), False)


class LaTeXPanel(QWidget):
    compile_requested = pyqtSignal(str)
    compile_finished = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker = None

        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)

        # Editor (left)
        self._editor = QPlainTextEdit()
        self._editor.setFont(font)
        self._editor.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #cccccc; border: 1px solid #333; }"
        )
        self._editor.setPlainText(_DEFAULT_TEX)
        self._highlighter = PygmentsHighlighter(self._editor.document(), "latex")

        # Preview (right)
        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self._preview_label.setStyleSheet("background: #1a1a1a;")
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._preview_label)
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { background: #1a1a1a; border: none; }")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._editor)
        splitter.addWidget(self._scroll)
        splitter.setSizes([500, 500])

        # Toolbar
        self._compile_btn = QPushButton("Compile")
        self._compile_btn.clicked.connect(self.compile)
        self._status = QLabel("Ready")
        self._status.setStyleSheet("color: #888888; padding: 0 8px;")
        self._error_btn = QPushButton("Errors ▼")
        self._error_btn.setCheckable(True)
        self._error_btn.toggled.connect(self._toggle_errors)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._compile_btn)
        toolbar.addWidget(self._status)
        toolbar.addStretch()
        toolbar.addWidget(self._error_btn)

        # Error panel
        self._error_panel = QPlainTextEdit()
        self._error_panel.setReadOnly(True)
        self._error_panel.setFont(font)
        self._error_panel.setFixedHeight(120)
        self._error_panel.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #f04040; border: 1px solid #333; }"
        )
        self._error_panel.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(splitter, stretch=1)
        layout.addLayout(toolbar)
        layout.addWidget(self._error_panel)

    def compile(self) -> None:
        source = self._editor.toPlainText()
        self.compile_requested.emit(source)
        self._compile_btn.setEnabled(False)
        self._status.setText("Compiling...")
        self._status.setStyleSheet("color: #f0c040; padding: 0 8px;")
        self._worker = _CompileWorker(source)
        self._worker.finished.connect(self._on_compile_done)
        self._worker.start()

    def _on_compile_done(self, result: str, success: bool) -> None:
        self._compile_btn.setEnabled(True)
        if success:
            self._status.setText("Done")
            self._status.setStyleSheet("color: #40c040; padding: 0 8px;")
            self._show_pdf_page(result)
            self.compile_finished.emit(True)
        else:
            self._status.setText("Failed")
            self._status.setStyleSheet("color: #f04040; padding: 0 8px;")
            self._error_panel.setPlainText(result)
            self._error_panel.setVisible(True)
            self._error_btn.setChecked(True)
            self.compile_finished.emit(False)

    def _show_pdf_page(self, pdf_path: str) -> None:
        try:
            import fitz
            doc = fitz.open(pdf_path)
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            img = QImage(pix.samples, pix.width, pix.height,
                         pix.stride, QImage.Format.Format_RGB888)
            self._preview_label.setPixmap(QPixmap.fromImage(img))
        except Exception as exc:
            _log.warning("PDF preview failed: %s", exc)

    def _toggle_errors(self, checked: bool) -> None:
        self._error_panel.setVisible(checked)
        self._error_btn.setText("Errors ▲" if checked else "Errors ▼")

    def load_content(self, content: str) -> None:
        self._editor.setPlainText(content)

    def get_content(self) -> str:
        return self._editor.toPlainText()
