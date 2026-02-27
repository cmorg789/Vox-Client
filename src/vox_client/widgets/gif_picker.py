"""GIF picker popup – search and select GIFs to send."""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QGridLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from vox_client.cache import media_cache
from vox_client.state import AppState
from vox_client.widgets.media_widgets import _get_nam, _pixmap_cache

log = logging.getLogger(__name__)

_COLS = 4
_THUMB_SIZE = 80


class GifPicker(QWidget):
    """Popup grid of GIFs with search, powered by server GIF proxy."""

    gif_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFixedSize(380, 420)
        self.setObjectName("GifPicker")

        self._fetch_generation: int = 0

        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(400)
        self._search_timer.timeout.connect(self._do_search)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search GIFs\u2026")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search_changed)
        root.addWidget(self._search)

        # Scroll area with grid
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        root.addWidget(self._scroll, stretch=1)

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(4)
        self._scroll.setWidget(self._grid_container)

        self._apply_styles()

    def show_at(self, global_pos) -> None:  # noqa: ANN001
        """Position above the button, clamped to screen."""
        screen = QGuiApplication.screenAt(global_pos)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() - self.height() - 4
        x = max(geo.left(), min(x, geo.right() - self.width()))
        y = max(geo.top(), min(y, geo.bottom() - self.height()))
        self.move(x, y)
        self.show()
        self._search.setFocus()
        self._search.clear()
        self._load_trending()

    def hideEvent(self, event) -> None:  # noqa: ANN001
        self._search_timer.stop()
        super().hideEvent(event)

    # -- search ----------------------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        self._search_timer.start()

    def _do_search(self) -> None:
        query = self._search.text().strip()
        if not query:
            self._load_trending()
        else:
            self._search_gifs(query)

    def _load_trending(self) -> None:
        self._fetch_generation += 1
        gen = self._fetch_generation
        asyncio.ensure_future(self._fetch_trending(gen))

    def _search_gifs(self, query: str) -> None:
        self._fetch_generation += 1
        gen = self._fetch_generation
        asyncio.ensure_future(self._fetch_search(query, gen))

    async def _fetch_trending(self, gen: int) -> None:
        client = AppState.instance().client
        if client is None:
            return
        try:
            resp = await client.gifs.trending(limit=20)
        except Exception:
            log.debug("GIF trending fetch failed", exc_info=True)
            return
        if gen != self._fetch_generation:
            return
        self._populate_grid(resp.results)

    async def _fetch_search(self, query: str, gen: int) -> None:
        client = AppState.instance().client
        if client is None:
            return
        try:
            resp = await client.gifs.search(query, limit=20)
        except Exception:
            log.debug("GIF search fetch failed", exc_info=True)
            return
        if gen != self._fetch_generation:
            return
        self._populate_grid(resp.results)

    def _populate_grid(self, results: list) -> None:
        # Clear existing
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        for i, result in enumerate(results):
            media = result.media_formats
            tiny = media.get("tinygif")
            full = media.get("gif")
            thumb_url = tiny.url if tiny else ""
            gif_url = (full.url if full else "") or thumb_url

            btn = QPushButton()
            btn.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(
                lambda checked, u=gif_url: self.gif_selected.emit(u)
            )
            self._grid_layout.addWidget(btn, i // _COLS, i % _COLS)

            if thumb_url:
                self._load_thumbnail(btn, thumb_url)

    def _load_thumbnail(self, btn: QPushButton, url: str) -> None:
        if url in _pixmap_cache:
            btn.setIcon(QIcon(_pixmap_cache[url]))
            btn.setIconSize(QSize(_THUMB_SIZE - 4, _THUMB_SIZE - 4))
            return
        cached = media_cache.get(url)
        if cached is not None:
            self._decode_and_apply(cached, btn, url)
            return
        req = QNetworkRequest(QUrl(url))
        nam = _get_nam()
        reply = nam.get(req)
        reply.finished.connect(
            lambda r=reply, b=btn, u=url: self._on_thumb_loaded(r, b, u)
        )

    def _on_thumb_loaded(
        self, reply: QNetworkReply, btn: QPushButton, url: str
    ) -> None:
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = bytes(reply.readAll())
                media_cache.put(url, data)
                self._decode_and_apply(data, btn, url)
        finally:
            reply.deleteLater()

    def _decode_and_apply(
        self, data: bytes, btn: QPushButton, url: str
    ) -> None:
        pm = QPixmap()
        pm.loadFromData(data)
        if not pm.isNull():
            scaled = pm.scaled(
                _THUMB_SIZE * 2,
                _THUMB_SIZE * 2,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(2)
            _pixmap_cache[url] = scaled
            try:
                btn.setIcon(QIcon(scaled))
                btn.setIconSize(QSize(_THUMB_SIZE - 4, _THUMB_SIZE - 4))
            except RuntimeError:
                pass  # Button already deleted by grid clear

    # -- styling ---------------------------------------------------------------

    def restyle(self) -> None:
        self._apply_styles()

    def _apply_styles(self) -> None:
        c = AppState.instance().theme.colors
        self.setStyleSheet(
            f"#GifPicker {{ background: {c.bg_panel}; border: 1px solid {c.border}; "
            f"border-radius: 8px; }}"
        )
        self._search.setStyleSheet(
            f"background: {c.bg_input}; color: {c.text_primary}; "
            f"border: 1px solid {c.border}; border-radius: 4px; padding: 6px;"
        )
        self._grid_container.setStyleSheet(
            f"QWidget {{ background: transparent; }}"
            f"QPushButton {{ background: {c.bg_input}; border: none; border-radius: 4px; }}"
            f"QPushButton:hover {{ background: {c.bg_hover}; }}"
        )
