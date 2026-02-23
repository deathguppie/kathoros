"""
ShellPanel — real interactive terminal via xterm embedded with -into.
X11 only. Falls back to an informative label if xterm is not found.

xterm is launched with -into <winId> so it lives inside the Qt widget tree.
The container widget uses WA_NativeWindow so it has a stable X11 window ID
before xterm is launched.

INV-18: this panel must never be imported by the router. The shell runs
entirely outside the router/tool-service path — it is a raw user terminal.
"""
import logging
import shlex
import shutil
from pathlib import Path

from PyQt6.QtCore import Qt, QProcess, QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)

_log = logging.getLogger("kathoros.ui.panels.shell_panel")

_XTERM_ARGS = [
    "-bg", "#1a1a1a",
    "-fg", "#cccccc",
    "-fa", "Monospace",
    "-fs", "11",
    "-title", "Kathoros Shell",
    "-bw", "0",       # no border
    "+sb",            # no scrollbar inside xterm (Qt handles scroll)
    "-bc",            # block cursor
]


class ShellPanel(QWidget):
    """Embeds an xterm process as a real interactive terminal."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._cwd: str | None = None
        self._xterm_path = shutil.which("xterm")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if not self._xterm_path:
            self._build_fallback_ui(layout)
            return

        # Toolbar: cwd label + restart button
        bar = QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 2)
        self._cwd_label = QLabel("~")
        self._cwd_label.setStyleSheet("color: #888888; font-size: 10px;")
        restart_btn = QPushButton("↺ Restart")
        restart_btn.setFixedWidth(80)
        restart_btn.setStyleSheet(
            "QPushButton { background: #2d2d2d; border: 1px solid #444; padding: 2px 6px; }"
        )
        restart_btn.clicked.connect(self._restart)
        bar.addWidget(self._cwd_label)
        bar.addStretch()
        bar.addWidget(restart_btn)

        bar_widget = QWidget()
        bar_widget.setLayout(bar)
        bar_widget.setFixedHeight(28)
        layout.addWidget(bar_widget)

        # Native container — WA_NativeWindow gives a real X11 WinId
        self._container = QWidget(self)
        self._container.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self._container.setStyleSheet("background: #1a1a1a;")
        layout.addWidget(self._container, stretch=1)

        # Delay launch until after the widget is fully shown and mapped
        QTimer.singleShot(250, self._launch)

        # Stop xterm on app quit (child widgets don't get closeEvent)
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().aboutToQuit.connect(self._stop)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_cwd(self, path: str) -> None:
        """Set working directory; restarts xterm in new dir if already running."""
        self._cwd = path
        label = getattr(self, "_cwd_label", None)
        if label:
            label.setText(path)
        if self._process and self._process.state() == QProcess.ProcessState.Running:
            self._restart()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _launch(self) -> None:
        if not self._xterm_path:
            return
        if self._process and self._process.state() == QProcess.ProcessState.Running:
            return

        wid = int(self._container.winId())
        args = ["-into", str(wid)] + _XTERM_ARGS

        if self._cwd:
            # Launch bash in the project directory
            init_cmd = f"cd {shlex.quote(self._cwd)}; exec bash --login"
            args += ["-e", "bash", "--login", "-c", init_cmd]

        self._process = QProcess(self)
        self._process.finished.connect(self._on_finished)
        self._process.start(self._xterm_path, args)

        if not self._process.waitForStarted(2000):
            _log.warning("xterm failed to start (path=%s)", self._xterm_path)

    @pyqtSlot()
    def _restart(self) -> None:
        self._stop()
        QTimer.singleShot(150, self._launch)

    def _stop(self) -> None:
        if self._process and self._process.state() == QProcess.ProcessState.Running:
            self._process.terminate()
            self._process.waitForFinished(1000)
            self._process = None

    @pyqtSlot(int, QProcess.ExitStatus)
    def _on_finished(self, exit_code: int, status) -> None:
        _log.debug("xterm exited: code=%d", exit_code)
        self._process = None

    def _build_fallback_ui(self, layout: QVBoxLayout) -> None:
        label = QLabel(
            "Shell unavailable: xterm not found.\n\n"
            "Install with:  sudo apt install xterm"
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #888888; padding: 20px;")
        layout.addWidget(label)
