"""
ShellPanel — embedded interactive terminal using a pseudo-terminal (pty).
Runs bash as a subprocess with stdin/stdout connected to a pty master fd.
Output is read asynchronously via QSocketNotifier and displayed in a
QPlainTextEdit. Input is sent from a QLineEdit with command history.

Works on X11 and Wayland. No external window dependencies.

INV-18: this panel must never be imported by the router. The shell runs
entirely outside the router/tool-service path — it is a raw user terminal.
"""
import logging
import os
import pty
import re
import signal
import subprocess

from PyQt6.QtCore import Qt, QSocketNotifier, pyqtSlot
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QLineEdit, QApplication,
)

_log = logging.getLogger("kathoros.ui.panels.shell_panel")

# Strip ANSI/VT100 escape sequences for plain-text display
_ANSI_RE = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


class ShellPanel(QWidget):
    """Embedded terminal: bash in a pty, output in QPlainTextEdit."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._process: subprocess.Popen | None = None
        self._master_fd: int | None = None
        self._notifier: QSocketNotifier | None = None
        self._cwd: str | None = None
        self._launched: bool = False
        self._history: list[str] = []
        self._hist_idx: int = -1

        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)

        # ── Toolbar ──────────────────────────────────────────────────────
        self._cwd_label = QLabel("~")
        self._cwd_label.setStyleSheet("color: #888888; font-size: 10px;")
        restart_btn = QPushButton("↺ Restart")
        restart_btn.setFixedWidth(80)
        restart_btn.setStyleSheet(
            "QPushButton { background: #2d2d2d; border: 1px solid #444; padding: 2px 6px; }"
        )
        restart_btn.clicked.connect(self._restart)

        bar = QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 2)
        bar.addWidget(self._cwd_label)
        bar.addStretch()
        bar.addWidget(restart_btn)
        bar_widget = QWidget()
        bar_widget.setLayout(bar)
        bar_widget.setFixedHeight(28)

        # ── Output area ──────────────────────────────────────────────────
        self._output = QPlainTextEdit()
        self._output.setReadOnly(False)   # programmatic insert needs writable
        self._output.setFont(font)
        self._output.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #cccccc; border: none; }"
        )
        # Block user from typing directly in the output pane
        self._output.installEventFilter(self)

        # ── Input row ────────────────────────────────────────────────────
        prompt = QLabel("$")
        prompt.setFont(font)
        prompt.setStyleSheet("color: #40c040; padding: 0 6px;")

        self._input = QLineEdit()
        self._input.setFont(font)
        self._input.setStyleSheet(
            "QLineEdit { background: #1a1a1a; color: #cccccc;"
            " border: 1px solid #333; padding: 2px 4px; }"
        )
        self._input.setPlaceholderText("command…")
        self._input.returnPressed.connect(self._send_input)
        self._input.installEventFilter(self)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.addWidget(prompt)
        input_row.addWidget(self._input, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bar_widget)
        layout.addWidget(self._output, stretch=1)
        layout.addLayout(input_row)

        QApplication.instance().aboutToQuit.connect(self._stop)

    # ── Public API ────────────────────────────────────────────────────────

    def set_cwd(self, path: str) -> None:
        self._cwd = path
        self._cwd_label.setText(path)
        # If already running, cd into the new directory
        if self._master_fd is not None:
            try:
                os.write(self._master_fd, f"cd {path}\n".encode())
            except OSError:
                pass

    # ── Qt overrides ──────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._launched:
            self._launched = True
            self._start()
        self._input.setFocus()

    def eventFilter(self, obj, event) -> bool:
        if obj is self._input and event.type() == event.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Up:
                self._history_navigate(1)
                return True
            if key == Qt.Key.Key_Down:
                self._history_navigate(-1)
                return True
            if (key == Qt.Key.Key_C and
                    event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self._send_bytes(b"\x03")   # SIGINT
                return True
            if (key == Qt.Key.Key_D and
                    event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self._send_bytes(b"\x04")   # EOF / logout
                return True
        # Swallow all key presses on the output pane
        if obj is self._output and event.type() == event.Type.KeyPress:
            # Allow Ctrl+C (copy) to pass through
            if (event.key() == Qt.Key.Key_C and
                    event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                return False
            return True
        return super().eventFilter(obj, event)

    # ── Internal ──────────────────────────────────────────────────────────

    def _start(self) -> None:
        try:
            master_fd, slave_fd = pty.openpty()
        except Exception as exc:
            _log.warning("pty.openpty() failed: %s", exc)
            self._append("[Terminal unavailable: pty not supported on this platform]\n")
            return

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"

        try:
            self._process = subprocess.Popen(
                ["bash", "--login"],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
                preexec_fn=os.setsid,
                cwd=self._cwd,
                env=env,
            )
        except Exception as exc:
            _log.warning("failed to start bash: %s", exc)
            os.close(master_fd)
            os.close(slave_fd)
            self._append(f"[Shell error: {exc}]\n")
            return

        os.close(slave_fd)       # parent only needs the master end
        self._master_fd = master_fd

        self._notifier = QSocketNotifier(
            master_fd, QSocketNotifier.Type.Read, self
        )
        self._notifier.activated.connect(self._on_data)
        _log.info("bash started pid=%d", self._process.pid)

    @pyqtSlot()
    def _on_data(self) -> None:
        try:
            data = os.read(self._master_fd, 4096)
        except OSError:
            if self._notifier:
                self._notifier.setEnabled(False)
            return
        text = data.decode("utf-8", errors="replace")
        text = _ANSI_RE.sub("", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        self._append(text)

    def _append(self, text: str) -> None:
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()

    def _send_input(self) -> None:
        cmd = self._input.text()
        self._input.clear()
        self._hist_idx = -1
        if cmd.strip():
            self._history.insert(0, cmd)
        self._send_bytes((cmd + "\n").encode("utf-8"))

    def _send_bytes(self, data: bytes) -> None:
        if self._master_fd is not None:
            try:
                os.write(self._master_fd, data)
            except OSError as exc:
                _log.warning("pty write failed: %s", exc)

    def _history_navigate(self, direction: int) -> None:
        if not self._history:
            return
        self._hist_idx = max(-1, min(len(self._history) - 1,
                                     self._hist_idx + direction))
        if self._hist_idx == -1:
            self._input.clear()
        else:
            self._input.setText(self._history[self._hist_idx])

    @pyqtSlot()
    def _restart(self) -> None:
        self._stop()
        self._output.clear()
        self._start()

    def _stop(self) -> None:
        if self._notifier:
            self._notifier.setEnabled(False)
            self._notifier = None
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None
        if self._process and self._process.poll() is None:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                self._process.wait(timeout=1)
            except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
                try:
                    self._process.kill()
                except OSError:
                    pass
            self._process = None
        _log.debug("shell stopped")
