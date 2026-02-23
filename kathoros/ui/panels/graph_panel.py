"""
GraphPanel — NetworkX graph visualizer with matplotlib embedding.
Displays causal graphs, concept networks, dependency graphs.
No DB calls. Load via load_graph() or build via add_node/add_edge.
"""
import logging
import matplotlib
matplotlib.use("QtAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import networkx as nx
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton
)
from PyQt6.QtCore import pyqtSignal

_log = logging.getLogger("kathoros.ui.panels.graph_panel")

_LAYOUTS = ["spring", "circular", "kamada_kawai", "shell"]


class GraphPanel(QWidget):
    node_selected = pyqtSignal(str)
    graph_changed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._graph = nx.DiGraph()

        # Toolbar
        self._layout_selector = QComboBox()
        self._layout_selector.addItems(_LAYOUTS)
        self._layout_selector.setFixedWidth(130)

        draw_btn = QPushButton("Draw")
        draw_btn.clicked.connect(self.draw)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear)

        self._status = QLabel("Nodes: 0, Edges: 0")
        self._status.setStyleSheet("color: #888888; padding: 0 8px; font-size: 11px;")

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._layout_selector)
        toolbar.addWidget(draw_btn)
        toolbar.addWidget(clear_btn)
        toolbar.addStretch()
        toolbar.addWidget(self._status)

        # Canvas
        self._fig = Figure(facecolor="#1a1a1a")
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setStyleSheet("background: #1a1a1a;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._canvas, stretch=1)

    def load_graph(self, graph: nx.Graph) -> None:
        self._graph = graph
        self._update_status()
        self.draw()
        self.graph_changed.emit()

    def add_node(self, node_id: str, label: str = "", **attrs) -> None:
        self._graph.add_node(node_id, label=label or node_id, **attrs)
        self._update_status()
        self.draw()
        self.graph_changed.emit()

    def add_edge(self, source: str, target: str, **attrs) -> None:
        self._graph.add_edge(source, target, **attrs)
        self._update_status()
        self.draw()
        self.graph_changed.emit()

    def clear(self) -> None:
        self._graph.clear()
        self._fig.clear()
        self._canvas.draw()
        self._update_status()
        self.graph_changed.emit()

    def draw(self) -> None:
        if self._graph.number_of_nodes() == 0:
            self._fig.clear()
            self._canvas.draw()
            return
        try:
            self._fig.clear()
            ax = self._fig.add_subplot(111)
            ax.set_facecolor("#1a1a1a")
            self._fig.patch.set_facecolor("#1a1a1a")
            pos = self._get_layout(self._layout_selector.currentText())
            labels = {n: self._graph.nodes[n].get("label", n) for n in self._graph.nodes}
            nx.draw(
                self._graph, pos, ax=ax,
                labels=labels,
                with_labels=True,
                node_color="#4090f0",
                edge_color="#666666",
                font_color="#cccccc",
                node_size=800,
                font_size=9,
                arrows=True,
            )
            self._canvas.draw()
        except Exception as exc:
            _log.warning("graph draw error: %s", exc)

    def _get_layout(self, name: str) -> dict:
        layouts = {
            "spring":       nx.spring_layout,
            "circular":     nx.circular_layout,
            "kamada_kawai": nx.kamada_kawai_layout,
            "shell":        nx.shell_layout,
        }
        fn = layouts.get(name, nx.spring_layout)
        return fn(self._graph)

    def _update_status(self) -> None:
        self._status.setText(
            f"Nodes: {self._graph.number_of_nodes()}, "
            f"Edges: {self._graph.number_of_edges()}"
        )
