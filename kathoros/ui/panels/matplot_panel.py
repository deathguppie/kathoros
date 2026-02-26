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
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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
            ax = self._fig.add_subplot(111)
            ax.set_facecolor("#1e1e1e")
            self._fig.patch.set_facecolor("#1a1a1a")

            # Build a thin plt-like wrapper that draws on our embedded figure
            _panel_fig = self._fig
            _panel_ax = ax

            class _PltProxy:
                """Routes plt.* calls to the embedded figure/axes."""
                def __getattr__(self, name):
                    # Axes-level functions: plot, scatter, bar, hist, etc.
                    if hasattr(_panel_ax, name):
                        return getattr(_panel_ax, name)
                    # Figure-level functions
                    if hasattr(_panel_fig, name):
                        return getattr(_panel_fig, name)
                    # Fall back to real plt for things like np imports
                    return getattr(plt, name)
                def figure(self, *a, **kw):
                    return _panel_fig
                def gcf(self):
                    return _panel_fig
                def gca(self):
                    return _panel_ax
                def subplot(self, *a, **kw):
                    return _panel_ax
                def subplots(self, *a, **kw):
                    return _panel_fig, _panel_ax
                def show(self):
                    pass  # no-op in embedded mode
                def title(self, *a, **kw):
                    _panel_ax.set_title(*a, **kw)
                def xlabel(self, *a, **kw):
                    _panel_ax.set_xlabel(*a, **kw)
                def ylabel(self, *a, **kw):
                    _panel_ax.set_ylabel(*a, **kw)
                def grid(self, *a, **kw):
                    _panel_ax.grid(*a, **kw)
                def legend(self, *a, **kw):
                    _panel_ax.legend(*a, **kw)
                def xlim(self, *a, **kw):
                    _panel_ax.set_xlim(*a, **kw)
                def ylim(self, *a, **kw):
                    _panel_ax.set_ylim(*a, **kw)
                def savefig(self, *a, **kw):
                    _panel_fig.savefig(*a, **kw)
                def close(self, *a, **kw):
                    pass  # no-op

            namespace = {
                "plt": _PltProxy(),
                "np": np,
                "fig": self._fig,
                "ax": ax,
            }
            exec(expr, namespace)  # noqa: S102
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
