"""
ShellPanel — embedded interactive terminal using a pseudo-terminal (pty).
Runs bash in a pty; the QPlainTextEdit both displays output and forwards
keystrokes to the pty so bash handles echo, history, and line editing.

Works on X11 and Wayland. No external window dependencies.

INV-18: this panel must never be imported by the router.
"""
import fcntl
import logging
import os
import pty
import re
import signal
import struct
import subprocess
import termios

from PyQt6.QtCore import Qt, QSocketNotifier, pyqtSlot
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QApplication,
)

_log = logging.getLogger("kathoros.ui.panels.shell_panel")

# Strip ANSI/VT100 colour and formatting codes for plain-text display.
# Cursor-movement sequences are also stripped; readline line-editing is
# therefore not visually accurate, but basic usage (type → Enter → output)
# works correctly.
_ANSI_RE = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


class ShellPanel(QWidget):
    """Single-pane embedded terminal: all typing happens in the output area."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._process: subprocess.Popen | None = None
        self._master_fd: int | None = None
        self._notifier: QSocketNotifier | None = None
        self._cwd: str | None = None
        self._launched: bool = False

        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)

        # ── Toolbar ──────────────────────────────────────────────────────
        self._cwd_label = QLabel("~")
        self._cwd_label.setStyleSheet("color: #888888; font-size: 10px;")
        restart_btn = QPushButton("↺ Restart")
        restart_btn.setFixedWidth(80)
        restart_btn.setStyleSheet(
            "QPushButton { background: #2d2d2d; border: 1px solid #444;"
            " padding: 2px 6px; }"
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

        # ── Terminal pane ────────────────────────────────────────────────
        self._output = QPlainTextEdit()
        self._output.setFont(font)
        self._output.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #cccccc; border: none; }"
        )
        self._output.setReadOnly(False)
        self._output.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bar_widget)
        layout.addWidget(self._output, stretch=1)

        QApplication.instance().aboutToQuit.connect(self._stop)

    # ── Public API ────────────────────────────────────────────────────────

    def set_cwd(self, path: str) -> None:
        self._cwd = path
        self._cwd_label.setText(path)
        if self._master_fd is not None:
            self._send_bytes(f"cd {path}\n".encode())

    # ── Qt overrides ──────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._launched:
            self._launched = True
            self._start()
        self._output.setFocus()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_pty_size()

    def eventFilter(self, obj, event) -> bool:
        if obj is self._output and event.type() == event.Type.KeyPress:
            return self._forward_key(event)
        return super().eventFilter(obj, event)

    # ── Key forwarding ────────────────────────────────────────────────────

    def _forward_key(self, event) -> bool:
        key  = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)

        # ── Ctrl combos ──────────────────────────────────────────────────
        if ctrl:
            mapping = {
                Qt.Key.Key_C: b"\x03",   # SIGINT
                Qt.Key.Key_D: b"\x04",   # EOF
                Qt.Key.Key_Z: b"\x1a",   # SIGTSTP
                Qt.Key.Key_L: b"\x0c",   # clear screen
                Qt.Key.Key_A: b"\x01",   # beginning of line
                Qt.Key.Key_E: b"\x05",   # end of line
                Qt.Key.Key_U: b"\x15",   # kill to beginning
                Qt.Key.Key_K: b"\x0b",   # kill to end
                Qt.Key.Key_W: b"\x17",   # delete word
            }
            if key in mapping:
                self._send_bytes(mapping[key])
                return True
            # Let Ctrl+C copy selected text through normally
            if key == Qt.Key.Key_C and self._output.textCursor().hasSelection():
                return False

        # ── Navigation / special keys ─────────────────────────────────
        specials = {
            Qt.Key.Key_Up:        b"\x1b[A",
            Qt.Key.Key_Down:      b"\x1b[B",
            Qt.Key.Key_Right:     b"\x1b[C",
            Qt.Key.Key_Left:      b"\x1b[D",
            Qt.Key.Key_Home:      b"\x1b[H",
            Qt.Key.Key_End:       b"\x1b[F",
            Qt.Key.Key_Delete:    b"\x1b[3~",
            Qt.Key.Key_PageUp:    b"\x1b[5~",
            Qt.Key.Key_PageDown:  b"\x1b[6~",
            Qt.Key.Key_Return:    b"\r",
            Qt.Key.Key_Enter:     b"\r",
            Qt.Key.Key_Backspace: b"\x7f",
            Qt.Key.Key_Tab:       b"\t",
            Qt.Key.Key_Escape:    b"\x1b",
        }
        if key in specials:
            self._send_bytes(specials[key])
            return True

        # ── Printable characters ─────────────────────────────────────
        text = event.text()
        if text:
            self._send_bytes(text.encode("utf-8"))
            return True

        return False

    # ── Internal ──────────────────────────────────────────────────────────

    def _start(self) -> None:
        try:
            master_fd, slave_fd = pty.openpty()
        except Exception as exc:
            _log.warning("pty.openpty() failed: %s", exc)
            self._append(f"[Terminal unavailable: {exc}]\n")
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

        os.close(slave_fd)
        self._master_fd = master_fd
        self._sync_pty_size()

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

    def _send_bytes(self, data: bytes) -> None:
        if self._master_fd is not None:
            try:
                os.write(self._master_fd, data)
            except OSError as exc:
                _log.warning("pty write failed: %s", exc)

    def _sync_pty_size(self) -> None:
        """Tell bash the current terminal dimensions via TIOCSWINSZ."""
        if self._master_fd is None:
            return
        try:
            fm = self._output.fontMetrics()
            vp = self._output.viewport()
            cols = max(1, vp.width()  // fm.horizontalAdvance("W"))
            rows = max(1, vp.height() // fm.height())
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)
        except Exception as exc:
            _log.debug("TIOCSWINSZ: %s", exc)

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
