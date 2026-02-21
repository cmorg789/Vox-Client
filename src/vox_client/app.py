"""Application controller – manages window lifecycle."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication

from vox_client.state import AppState
from vox_client.theme import Theme, load_saved_hue
from vox_client.views.main_window import MainWindow

_FONTS_DIR = Path(__file__).parent / "resources" / "fonts"


def _load_bundled_fonts() -> None:
    """Register bundled TTF fonts with Qt's font database."""
    if not _FONTS_DIR.is_dir():
        return
    for ttf in _FONTS_DIR.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(ttf))


class VoxApp:
    """Owns the QApplication and shows the main window directly."""

    def __init__(self, qt_app: QApplication) -> None:
        self.qt_app = qt_app
        self.main_window: MainWindow | None = None

        # Load bundled fonts before applying theme (so QSS font-family resolves)
        _load_bundled_fonts()

        # Theme setup
        state = AppState.instance()
        hue = load_saved_hue()
        state.theme = Theme(hue)
        self.qt_app.setStyleSheet(state.theme.generate_qss())

        # Re-apply QSS when theme changes
        state.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        state = AppState.instance()
        if state.theme:
            self.qt_app.setStyleSheet(state.theme.generate_qss())

    # -- window management ---------------------------------------------------

    def show_main(self) -> None:
        """Create and show the main window, then try restoring a saved session."""
        self.main_window = MainWindow()
        self.main_window.show()
        self.main_window.try_restore_session()
