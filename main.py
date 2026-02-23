"""
Kathoros — entry point.
Launches project selector then main window.
No business logic here.
"""
import sys
import logging
import time
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QTimer, QEventLoop
from kathoros.ui.main_window import KathorosMainWindow
from kathoros.ui.dialogs.project_dialog import ProjectDialog
from kathoros.services.project_manager import ProjectManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
_log = logging.getLogger("kathoros.main")

_LOGO = Path(__file__).parent / "kathoros" / "assets" / "logo.jpg"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Kathoros")
    app.setOrganizationName("Kathoros")

    # Splash screen — minimum 1.5 s display regardless of load speed
    splash = None
    splash_start = 0.0
    _SPLASH_MIN_MS = 1500
    if _LOGO.exists():
        pix = QPixmap(str(_LOGO))
        if not pix.isNull():
            screen = app.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                max_w = min(pix.width(), int(avail.width() * 0.6))
                pix = pix.scaledToWidth(max_w, Qt.TransformationMode.SmoothTransformation)
            splash = QSplashScreen(pix, Qt.WindowType.WindowStaysOnTopHint)
            splash.show()
            app.processEvents()
            splash_start = time.monotonic()
    app.setStyleSheet("""
        QWidget { background-color: #1e1e1e; color: #cccccc; }
        QTabBar::tab { background: #2d2d2d; color: #cccccc; padding: 6px 12px; }
        QTabBar::tab:selected { background: #3d3d3d; }
        QSplitter::handle { background: #333333; }
        QListWidget { background: #252525; border: 1px solid #333; }
        QLineEdit { background: #252525; border: 1px solid #444; padding: 4px; }
        QPushButton { background: #2d2d2d; border: 1px solid #444; padding: 6px 12px; }
        QPushButton:hover { background: #3d3d3d; }
        QDialog { background: #1e1e1e; }
    """)

    pm = ProjectManager()
    pm.open_global()

    if splash:
        # Hold splash for remainder of minimum display time
        elapsed_ms = int((time.monotonic() - splash_start) * 1000)
        remaining = _SPLASH_MIN_MS - elapsed_ms
        if remaining > 0:
            loop = QEventLoop()
            QTimer.singleShot(remaining, loop.quit)
            loop.exec()
        splash.finish(None)

    dialog = ProjectDialog(pm)
    if dialog.exec() != ProjectDialog.DialogCode.Accepted:
        _log.info("no project selected — exiting")
        return 0

    window = KathorosMainWindow(project_manager=pm)
    window.show()
    _log.info("Kathoros started — project: %s", pm.project_name)

    result = app.exec()
    pm.close()
    return result


if __name__ == "__main__":
    sys.exit(main())
