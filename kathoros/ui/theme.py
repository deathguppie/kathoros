"""
System theme detection with app dark-theme fallback.
"""
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication

# Built-in dark stylesheet (fallback when system has no dark theme)
_DARK_STYLESHEET = """
    QWidget { background-color: #1e1e1e; color: #cccccc; }
    QTabBar::tab { background: #2d2d2d; color: #cccccc; padding: 6px 12px; }
    QTabBar::tab:selected { background: #3d3d3d; }
    QSplitter::handle { background: #333333; }
    QListWidget { background: #252525; border: 1px solid #333; }
    QLineEdit { background: #252525; border: 1px solid #444; padding: 4px; }
    QPushButton { background: #2d2d2d; border: 1px solid #444; padding: 6px 12px; }
    QPushButton:hover { background: #3d3d3d; }
    QDialog { background: #1e1e1e; }
"""

_system_is_dark: bool | None = None


def detect_system_dark() -> bool:
    """Check whether the platform's default palette is already dark."""
    bg = QApplication.palette().color(QPalette.ColorRole.Window)
    # ITU-R BT.601 luminance
    luminance = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
    return luminance < 128


def apply_theme(app: QApplication) -> None:
    """Apply the app dark stylesheet only if the system theme isn't dark."""
    global _system_is_dark
    _system_is_dark = detect_system_dark()
    if not _system_is_dark:
        app.setStyleSheet(_DARK_STYLESHEET)


def use_app_theme() -> bool:
    """Return True if the app's built-in dark stylesheet is active."""
    if _system_is_dark is None:
        return True  # safe default before apply_theme() runs
    return not _system_is_dark
