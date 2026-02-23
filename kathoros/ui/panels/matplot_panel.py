"""
MatPlotPanel — embedded matplotlib figure display.
Researcher writes matplotlib code, clicks Run, sees plot inline.
No DB calls.
"""
import logging
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QFileDialog
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont

_log = logging.getLogger("kathoros.ui.panels.matplot_panel")

_DEFAULT_CODE = "import numpy as np\nx = np.linspace(0, 2*np.pi, 100)\nplt.plot(x, np.sin(x))\nplt.title('sin(x)')"


class MatPlotPanel(QWidget):
    plot_ready = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Toolbar
        run_btn = QPushButton("Run")
        run_btn.clicked.connect(self.run_code)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save_clicked)

        toolbar = QHBoxLayout()
        toolbar.addWidget(run_btn)
        toolbar.addWidget(clear_btn)
        toolbar.addStretch()
        toolbar.addWidget(save_btn)

        # Code input
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)

        self._code_input = QPlainTextEdit()
        self._code_input.setFixedHeight(110)
        self._code_input.setPlaceholderText(_DEFAULT_CODE)
        self._code_input.setFont(font)
        self._code_input.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #cccccc; border: 1px solid #333; }"
        )

        # Canvas
        self._fig = Figure(facecolor="#1a1a1a")
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setStyleSheet("background: #1a1a1a;")

        self._status = QLabel("Ready")
        self._status.setStyleSheet("color: #888888; padding: 2px 4px; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._code_input)
        layout.addWidget(self._canvas, stretch=1)
        layout.addWidget(self._status)

    def run_code(self, code: str = "") -> None:
        expr = code or self._code_input.toPlainText().strip()
        if not expr:
            return
        try:
            import numpy as np
            self._fig.clear()
            namespace = {
                "plt": plt,
                "np": np,
                "fig": self._fig,
            }
            # redirect plt to use our figure
            plt.figure(self._fig.number if self._fig.number else 1)
            exec(expr, namespace)  # noqa: S102
            self._canvas.figure = plt.gcf()
            self._canvas.draw()
            self._status.setText("Done")
            self._status.setStyleSheet("color: #40c040; padding: 2px 4px; font-size: 11px;")
            self.plot_ready.emit()
        except Exception as exc:
            _log.warning("matplot exec error: %s", exc)
            self._status.setText(f"Error: {exc}")
            self._status.setStyleSheet("color: #f04040; padding: 2px 4px; font-size: 11px;")
            self.error_occurred.emit(str(exc))

    def clear(self) -> None:
        self._fig.clear()
        self._canvas.draw()
        self._code_input.clear()
        self._status.setText("Ready")
        self._status.setStyleSheet("color: #888888; padding: 2px 4px; font-size: 11px;")

    def save_figure(self, path: str) -> None:
        try:
            self._canvas.figure.savefig(path, facecolor="#1a1a1a")
            self._status.setText(f"Saved: {path.split('/')[-1]}")
        except Exception as exc:
            _log.warning("save failed: %s", exc)
            self.error_occurred.emit(str(exc))

    def _on_save_clicked(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Figure", "", "PNG Files (*.png);;PDF Files (*.pdf)"
        )
        if path:
            self.save_figure(path)
