"""Application controller – manages window lifecycle."""

from __future__ import annotations

import logging

from PyQt6.QtGui import QFontDatabase, QIcon
from PyQt6.QtWidgets import QApplication

from vox_client._frozen import APP_ICON as _APP_ICON, FONTS_DIR as _FONTS_DIR
from vox_client.state import AppState
from vox_client.theme import Theme, load_saved_flavor
from vox_client.views.main_window import MainWindow

log = logging.getLogger(__name__)


def _load_bundled_fonts() -> None:
    """Register bundled TTF fonts with Qt's font database."""
    if not _FONTS_DIR.is_dir():
        log.debug("Fonts directory not found: %s", _FONTS_DIR)
        return
    for ttf in _FONTS_DIR.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(ttf))
    log.debug("Loaded bundled fonts from %s", _FONTS_DIR)


class VoxApp:
    """Owns the QApplication and shows the main window directly."""

    def __init__(self, qt_app: QApplication) -> None:
        self.qt_app = qt_app
        self.main_window: MainWindow | None = None

        log.info("Initializing VoxApp")

        # Load bundled fonts before applying theme (so QSS font-family resolves)
        _load_bundled_fonts()

        # Theme setup
        state = AppState.instance()
        flavor = load_saved_flavor()
        log.info("Applying theme flavor: %s", flavor)
        state.theme = Theme(flavor)
        self.qt_app.setStyleSheet(state.theme.generate_qss())

        # Application icon
        if _APP_ICON.exists():
            self.qt_app.setWindowIcon(QIcon(str(_APP_ICON)))

        # Re-apply QSS when theme changes
        state.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        state = AppState.instance()
        if state.theme:
            log.info("Theme changed to %s", state.theme.flavor)
            self.qt_app.setStyleSheet(state.theme.generate_qss())

    # -- window management ---------------------------------------------------

    def show_main(self) -> None:
        """Create and show the main window, then try restoring a saved session."""
        self.main_window = MainWindow()
        self.main_window.show()
        self.main_window.try_restore_session()
