"""
ReaderPanel — PDF viewer using pymupdf (fitz).
Three-class architecture:
  PageRenderer  — background QThread worker (owns its own fitz.Document)
  PageWidget    — custom widget with text-selection rubber-band
  ReaderPanel   — main panel wiring toolbar, scroll area, zoom bar
"""
import logging
from pathlib import Path

import fitz  # pymupdf
from PyQt6.QtCore import (
    QObject,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import (
    QCursor,
    QGuiApplication,
    QImage,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_log = logging.getLogger("kathoros.ui.panels.reader_panel")

_ZOOM_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]


# ---------------------------------------------------------------------------
# Background renderer
# ---------------------------------------------------------------------------

class PageRenderer(QObject):
    """Renders PDF pages in a dedicated thread using its own fitz.Document."""

    page_ready = pyqtSignal(int, QImage, float)   # page_num, image, zoom

    def __init__(self) -> None:
        super().__init__()
        self._doc: fitz.Document | None = None
        self._doc_path: str | None = None
        self._pending: dict | None = None   # latest queued request
        self._busy = False

    # Called from main thread via queued connection -------------------------

    @pyqtSlot(str, int, float)
    def render(self, path: str, page_num: int, zoom: float) -> None:
        if self._busy:
            # Stash latest; current render finishes then picks this up
            self._pending = {"path": path, "page_num": page_num, "zoom": zoom}
            return
        self._do_render(path, page_num, zoom)
        # Process any pending request that arrived while we were busy
        while self._pending is not None:
            req = self._pending
            self._pending = None
            self._do_render(req["path"], req["page_num"], req["zoom"])

    def _do_render(self, path: str, page_num: int, zoom: float) -> None:
        self._busy = True
        try:
            if self._doc_path != path:
                if self._doc:
                    self._doc.close()
                self._doc = fitz.open(path)
                self._doc_path = path

            if self._doc is None or not (0 <= page_num < len(self._doc)):
                return

            page = self._doc.load_page(page_num)
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = QImage(
                pix.samples_mv,
                pix.width, pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            )
            self.page_ready.emit(page_num, img.copy(), zoom)
        except Exception as exc:
            _log.warning("render error page=%d: %s", page_num, exc)
        finally:
            self._busy = False

    def close_doc(self) -> None:
        if self._doc:
            self._doc.close()
            self._doc = None
            self._doc_path = None


# ---------------------------------------------------------------------------
# Page display widget with rubber-band text selection
# ---------------------------------------------------------------------------

class PageWidget(QWidget):
    """Displays a single PDF page; supports mouse rubber-band text selection."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: #1a1a1a;")
        self.setCursor(QCursor(Qt.CursorShape.IBeamCursor))

        self._pixmap: QPixmap | None = None
        self._zoom: float = 1.0
        self._fitz_page: fitz.Page | None = None

        self._sel_start: tuple[int, int] | None = None
        self._sel_end:   tuple[int, int] | None = None
        self._selecting = False

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # Public API ------------------------------------------------------------

    def set_page(self, pixmap: QPixmap, zoom: float, fitz_page: fitz.Page) -> None:
        self._pixmap = pixmap
        self._zoom = zoom
        self._fitz_page = fitz_page
        self._sel_start = self._sel_end = None
        self.resize(pixmap.size())
        self.update()

    # Paint -----------------------------------------------------------------

    def paintEvent(self, event) -> None:
        from PyQt6.QtGui import QColor, QPainter
        painter = QPainter(self)
        if self._pixmap:
            # Centre pixmap in widget
            x = max(0, (self.width()  - self._pixmap.width())  // 2)
            y = max(0, (self.height() - self._pixmap.height()) // 2)
            painter.drawPixmap(x, y, self._pixmap)

            if self._sel_start and self._sel_end:
                x0, y0 = self._sel_start
                x1, y1 = self._sel_end
                # Absolute coords within pixmap area
                rx = min(x0, x1) + x
                ry = min(y0, y1) + y
                rw = abs(x1 - x0)
                rh = abs(y1 - y0)
                from PyQt6.QtCore import QRect
                sel_color = QColor(100, 149, 237, 80)
                painter.fillRect(QRect(rx, ry, rw, rh), sel_color)
        painter.end()

    # Mouse events ----------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pixmap:
            pos = self._widget_to_page(event.position())
            self._sel_start = pos
            self._sel_end = pos
            self._selecting = True
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._selecting and self._pixmap:
            self._sel_end = self._widget_to_page(event.position())
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._selecting = False
            if self._sel_start and self._sel_end:
                self._copy_selection_text()

    # Helpers ---------------------------------------------------------------

    def _widget_to_page(self, qpointf) -> tuple[int, int]:
        """Convert widget-local coords to coords relative to page pixmap origin."""
        if self._pixmap is None:
            return (0, 0)
        px_origin_x = max(0, (self.width()  - self._pixmap.width())  // 2)
        px_origin_y = max(0, (self.height() - self._pixmap.height()) // 2)
        x = int(qpointf.x()) - px_origin_x
        y = int(qpointf.y()) - px_origin_y
        return (x, y)

    def _copy_selection_text(self) -> None:
        if not (self._fitz_page and self._sel_start and self._sel_end):
            return
        x0, y0 = self._sel_start
        x1, y1 = self._sel_end
        if x0 == x1 or y0 == y1:
            return
        # Convert pixel coords → PDF coords (divide by zoom)
        z = self._zoom
        rect = fitz.Rect(
            min(x0, x1) / z, min(y0, y1) / z,
            max(x0, x1) / z, max(y0, y1) / z,
        )
        try:
            words = self._fitz_page.get_text("words", clip=rect)
            # words: (x0,y0,x1,y1,word,block_no,line_no,word_no)
            words_sorted = sorted(words, key=lambda w: (w[5], w[6], w[7]))
            text = " ".join(w[4] for w in words_sorted)
            if text.strip():
                QGuiApplication.clipboard().setText(text.strip())
                _log.debug("copied %d chars to clipboard", len(text))
        except Exception as exc:
            _log.warning("text extraction error: %s", exc)


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

class ReaderPanel(QWidget):
    """Full PDF viewer panel: fit-to-width, background rendering, text selection."""

    page_changed = pyqtSignal(int)
    render_requested = pyqtSignal(str, int, float)  # path, page_num, zoom

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # State
        self._doc_path: str | None = None
        self._doc: fitz.Document | None = None
        self._current_page = 0
        self._total_pages = 0
        self._fit_width: bool = True
        self._explicit_zoom: float = 1.5

        # Resize debounce
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._request_render)

        # Background renderer thread
        self._render_thread = QThread(self)
        self._renderer = PageRenderer()
        self._renderer.moveToThread(self._render_thread)
        self._renderer.page_ready.connect(self._on_page_ready)
        self.render_requested.connect(self._renderer.render)
        self._render_thread.start()

        # Stop thread on app quit (closeEvent is not called for child widgets)
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().aboutToQuit.connect(self._stop_render_thread)

        self._build_ui()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Toolbar
        open_btn = QPushButton("Open PDF")
        open_btn.clicked.connect(self._on_open)

        self._filename_label = QLabel("No file loaded")
        self._filename_label.setStyleSheet("color: #888888; padding: 0 8px;")
        self._filename_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        self._prev_btn = QPushButton("◀")
        self._prev_btn.setFixedWidth(32)
        self._prev_btn.clicked.connect(self.prev_page)
        self._prev_btn.setEnabled(False)

        self._page_input = QLineEdit()
        self._page_input.setFixedWidth(48)
        self._page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_input.returnPressed.connect(self._on_page_jump)

        self._total_label = QLabel("/ —")
        self._total_label.setMinimumWidth(40)

        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedWidth(32)
        self._next_btn.clicked.connect(self.next_page)
        self._next_btn.setEnabled(False)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.addWidget(open_btn)
        toolbar.addWidget(self._filename_label)
        toolbar.addStretch()
        toolbar.addWidget(self._prev_btn)
        toolbar.addWidget(self._page_input)
        toolbar.addWidget(self._total_label)
        toolbar.addWidget(self._next_btn)

        # Scroll area + page widget
        self._page_widget = PageWidget()
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._page_widget)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setStyleSheet("QScrollArea { background: #1a1a1a; border: none; }")

        # Zoom bar
        self._fit_btn = QPushButton("Fit Width")
        self._fit_btn.setCheckable(True)
        self._fit_btn.setChecked(True)
        self._fit_btn.clicked.connect(self._on_fit_clicked)

        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedWidth(28)
        zoom_out_btn.clicked.connect(self._zoom_out)

        self._zoom_label = QLabel("Fit")
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_label.setMinimumWidth(48)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedWidth(28)
        zoom_in_btn.clicked.connect(self._zoom_in)

        zoom_bar = QHBoxLayout()
        zoom_bar.setContentsMargins(0, 0, 0, 0)
        zoom_bar.addStretch()
        zoom_bar.addWidget(self._fit_btn)
        zoom_bar.addWidget(zoom_out_btn)
        zoom_bar.addWidget(self._zoom_label)
        zoom_bar.addWidget(zoom_in_btn)
        zoom_bar.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addLayout(toolbar)
        layout.addWidget(self._scroll, stretch=1)
        layout.addLayout(zoom_bar)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_pdf(self, path: str) -> None:
        try:
            if self._doc:
                self._doc.close()
            self._doc = fitz.open(path)
            self._doc_path = path
            self._total_pages = len(self._doc)
            self._current_page = 0
            name = Path(path).name
            self._filename_label.setText(name)
            self._total_label.setText(f"/ {self._total_pages}")
            self._prev_btn.setEnabled(False)
            self._next_btn.setEnabled(self._total_pages > 1)
            self._request_render()
        except Exception as exc:
            _log.warning("failed to load PDF %s: %s", path, exc)
            self.clear()

    def show_page(self, page_num: int) -> None:
        if self._doc is None or not (0 <= page_num < self._total_pages):
            return
        self._current_page = page_num
        self._page_input.setText(str(page_num + 1))
        self._prev_btn.setEnabled(page_num > 0)
        self._next_btn.setEnabled(page_num < self._total_pages - 1)
        self._request_render()

    def next_page(self) -> None:
        if self._current_page < self._total_pages - 1:
            self.show_page(self._current_page + 1)

    def prev_page(self) -> None:
        if self._current_page > 0:
            self.show_page(self._current_page - 1)

    def set_zoom(self, factor: float) -> None:
        self._explicit_zoom = factor
        self._fit_width = False
        self._fit_btn.setChecked(False)
        self._zoom_label.setText(f"{int(factor * 100)}%")
        self._request_render()

    def clear(self) -> None:
        self._page_widget.set_page(QPixmap(), 1.0, None)
        self._filename_label.setText("No file loaded")
        self._page_input.clear()
        self._total_label.setText("/ —")
        self._current_page = 0
        self._total_pages = 0
        self._prev_btn.setEnabled(False)
        self._next_btn.setEnabled(False)
        if self._doc:
            self._doc.close()
            self._doc = None
            self._doc_path = None

    # ------------------------------------------------------------------
    # Zoom helpers
    # ------------------------------------------------------------------

    def _compute_zoom(self, page: fitz.Page | None = None) -> float:
        if self._fit_width and self._doc:
            if page is None:
                page = self._doc.load_page(self._current_page)
            avail = max(100, self._scroll.viewport().width() - 4)
            return avail / page.rect.width
        return self._explicit_zoom

    def _zoom_in(self) -> None:
        current = self._compute_zoom()
        for step in _ZOOM_STEPS:
            if step > current + 0.001:
                self.set_zoom(step)
                return
        # Already at max
        self.set_zoom(_ZOOM_STEPS[-1])

    def _zoom_out(self) -> None:
        current = self._compute_zoom()
        for step in reversed(_ZOOM_STEPS):
            if step < current - 0.001:
                self.set_zoom(step)
                return
        self.set_zoom(_ZOOM_STEPS[0])

    def _on_fit_clicked(self) -> None:
        checked = self._fit_btn.isChecked()
        self._fit_width = checked
        if checked:
            self._zoom_label.setText("Fit")
        else:
            self._zoom_label.setText(f"{int(self._explicit_zoom * 100)}%")
        if self._doc:
            self._request_render()

    # ------------------------------------------------------------------
    # Render pipeline
    # ------------------------------------------------------------------

    def _request_render(self) -> None:
        if self._doc_path is None or self._doc is None:
            return
        zoom = self._compute_zoom()
        self.render_requested.emit(self._doc_path, self._current_page, zoom)

    @pyqtSlot(int, QImage, float)
    def _on_page_ready(self, page_num: int, image: QImage, zoom: float) -> None:
        # Only display if this is still the current page
        if page_num != self._current_page or self._doc is None:
            return
        pixmap = QPixmap.fromImage(image)
        fitz_page = self._doc.load_page(page_num)
        self._page_widget.set_page(pixmap, zoom, fitz_page)
        # Scroll to top after page change
        self._scroll.verticalScrollBar().setValue(0)
        # Update labels
        self._page_input.setText(str(page_num + 1))
        if self._fit_width:
            self._zoom_label.setText("Fit")
        else:
            self._zoom_label.setText(f"{int(zoom * 100)}%")
        self.page_changed.emit(page_num)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit_width and self._doc:
            self._resize_timer.start()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Space):
            self.next_page()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp):
            self.prev_page()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._zoom_in()
        elif key == Qt.Key.Key_Minus:
            self._zoom_out()
        else:
            super().keyPressEvent(event)

    def _on_page_jump(self) -> None:
        text = self._page_input.text().strip()
        try:
            n = int(text)
        except ValueError:
            self._page_input.setText(str(self._current_page + 1))
            return
        if 1 <= n <= self._total_pages:
            self.show_page(n - 1)
        else:
            self._page_input.setText(str(self._current_page + 1))

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF", "", "PDF Files (*.pdf);;All Files (*)"
        )
        if path:
            self.load_pdf(path)

    def _stop_render_thread(self) -> None:
        if self._render_thread.isRunning():
            self._render_thread.quit()
            self._render_thread.wait(2000)
        self._renderer.close_doc()
        if self._doc:
            self._doc.close()
            self._doc = None

    def closeEvent(self, event) -> None:
        self._stop_render_thread()
        super().closeEvent(event)
