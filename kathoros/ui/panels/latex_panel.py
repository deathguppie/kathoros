"""
LaTeXPanel — LaTeX editor with pdflatex compilation.
On success emits pdf_ready(path) so the main window can open the PDF in the reader.
No DB calls.
"""
import logging
import subprocess
import tempfile
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QPushButton, QLabel
)
from PyQt6.QtCore import pyqtSignal, QThread
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
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
    compile_done = pyqtSignal(str, bool)  # (pdf_path_or_error, success)

    def __init__(self, source: str) -> None:
        super().__init__()
        self._source = source

    def run(self) -> None:
        import logging
        log = logging.getLogger("kathoros.latex.worker")
        tmp_dir = tempfile.mkdtemp()
        tex_path = os.path.join(tmp_dir, "doc.tex")
        pdf_path = os.path.join(tmp_dir, "doc.pdf")
        log.info("pdflatex start tmp_dir=%s", tmp_dir)
        try:
            with open(tex_path, "w") as f:
                f.write(self._source)
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode",
                 f"-output-directory={tmp_dir}", tex_path],
                capture_output=True, text=True, timeout=30,
            )
            exists = os.path.exists(pdf_path)
            size = os.path.getsize(pdf_path) if exists else 0
            log.info("pdflatex done rc=%d pdf_exists=%s pdf_size=%d", result.returncode, exists, size)
            if exists:
                self.compile_done.emit(pdf_path, True)
            else:
                log.warning("pdflatex stdout: %s", result.stdout[-300:])
                self.compile_done.emit(result.stdout + result.stderr, False)
        except subprocess.TimeoutExpired:
            self.compile_done.emit("Compile timed out (30s)", False)
        except Exception as exc:
            self.compile_done.emit(str(exc), False)


class LaTeXPanel(QWidget):
    compile_requested = pyqtSignal(str)
    compile_finished = pyqtSignal(bool)
    pdf_ready = pyqtSignal(str)   # emitted with PDF path on successful compile

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker = None

        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)

        self._editor = QPlainTextEdit()
        self._editor.setFont(font)
        self._editor.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #cccccc; border: 1px solid #333; }"
        )
        self._editor.setPlainText(_DEFAULT_TEX)
        self._highlighter = PygmentsHighlighter(self._editor.document(), "latex")

        self._compile_btn = QPushButton("Compile  [F5]")
        self._compile_btn.clicked.connect(self.compile)
        self._shortcut = QShortcut(QKeySequence("F5"), self)
        self._shortcut.activated.connect(self.compile)
        self._status = QLabel("Ready")
        self._status.setStyleSheet("color: #888888; padding: 0 8px;")
        self._error_btn = QPushButton("Errors ▼")
        self._error_btn.setCheckable(True)
        self._error_btn.toggled.connect(self._toggle_errors)

        self._toolbar = QWidget()
        toolbar = QHBoxLayout(self._toolbar)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.addWidget(self._compile_btn)
        toolbar.addWidget(self._status)
        toolbar.addStretch()
        toolbar.addWidget(self._error_btn)

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
        layout.addWidget(self._editor, stretch=1)
        layout.addWidget(self._toolbar)
        layout.addWidget(self._error_panel)

    def compile(self) -> None:
        source = self._editor.toPlainText()
        # Auto-wrap fragments that lack a documentclass
        if r"\documentclass" not in source:
            source = (
                r"\documentclass{article}" + "\n"
                r"\usepackage{amsmath,amssymb,amsthm}" + "\n"
                r"\begin{document}" + "\n"
                + source + "\n"
                r"\end{document}" + "\n"
            )
        _log.info("compile() called, source length=%d", len(source))
        self.compile_requested.emit(source)
        self._compile_btn.setEnabled(False)
        self._status.setText("Compiling...")
        self._status.setStyleSheet("color: #f0c040; padding: 0 8px;")
        self._worker = _CompileWorker(source)
        self._worker.compile_done.connect(self._on_compile_done)
        self._worker.start()

    def _on_compile_done(self, result: str, success: bool) -> None:
        _log.info("compile done: success=%s", success)
        self._compile_btn.setEnabled(True)
        if success:
            self._status.setText("Done")
            self._status.setStyleSheet("color: #40c040; padding: 0 8px;")
            _log.info("emitting pdf_ready: %s", result)
            self.pdf_ready.emit(result)
            self.compile_finished.emit(True)
        else:
            self._status.setText("Failed")
            self._status.setStyleSheet("color: #f04040; padding: 0 8px;")
            self._error_panel.setPlainText(result)
            self._error_panel.setVisible(True)
            self._error_btn.setChecked(True)
            self.compile_finished.emit(False)

    def _toggle_errors(self, checked: bool) -> None:
        self._error_panel.setVisible(checked)
        self._error_btn.setText("Errors ▲" if checked else "Errors ▼")

    def load_content(self, content: str) -> None:
        content = content.strip()
        if not content:
            self._editor.setPlainText(_DEFAULT_TEX)
            return
        if r"\documentclass" not in content:
            content = (
                r"\documentclass{article}" + "\n"
                r"\usepackage{amsmath,amssymb,amsthm}" + "\n"
                r"\begin{document}" + "\n"
                + content + "\n"
                r"\end{document}" + "\n"
            )
        self._editor.setPlainText(content)

    def get_content(self) -> str:
        return self._editor.toPlainText()
