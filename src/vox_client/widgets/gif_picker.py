"""Tenor GIF picker popup – search and select GIFs to send."""

from __future__ import annotations

import json
import logging
from urllib.parse import quote

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from vox_client.state import AppState

log = logging.getLogger(__name__)

_TENOR_API_KEY = "LIVDSRZULELA"
_TENOR_BASE = "https://tenor.googleapis.com/v2"
_COLS = 4
_THUMB_SIZE = 80


class GifPicker(QWidget):
    """Popup grid of GIFs with search, powered by Tenor API v2."""

    gif_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFixedSize(380, 420)
        self.setObjectName("GifPicker")

        self._nam = QNetworkAccessManager(self)
        self._thumb_cache: dict[str, QPixmap] = {}
        self._current_reply: QNetworkReply | None = None

        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(400)
        self._search_timer.timeout.connect(self._do_search)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search Tenor\u2026")
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

    # -- search ----------------------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        self._search_timer.start()

    def _do_search(self) -> None:
        query = self._search.text().strip()
        if not query:
            self._load_trending()
        else:
            self._search_tenor(query)

    def _load_trending(self) -> None:
        url = (
            f"{_TENOR_BASE}/featured?key={_TENOR_API_KEY}"
            f"&limit=20&media_filter=tinygif,gif"
        )
        self._fetch_results(url)

    def _search_tenor(self, query: str) -> None:
        url = (
            f"{_TENOR_BASE}/search?key={_TENOR_API_KEY}"
            f"&q={quote(query)}&limit=20&media_filter=tinygif,gif"
        )
        self._fetch_results(url)

    def _fetch_results(self, url: str) -> None:
        # Abort any in-flight request to prevent stale results overwriting newer ones
        if self._current_reply is not None:
            self._current_reply.abort()
            self._current_reply.deleteLater()
            self._current_reply = None
        req = QNetworkRequest(QUrl(url))
        reply = self._nam.get(req)
        self._current_reply = reply
        reply.finished.connect(lambda r=reply: self._on_results(r))

    def _on_results(self, reply: QNetworkReply) -> None:
        # Ignore stale replies that were superseded
        if reply is not self._current_reply:
            reply.deleteLater()
            return
        self._current_reply = None
        if reply.error() != QNetworkReply.NetworkError.NoError:
            log.debug("Tenor fetch failed: %s", reply.errorString())
            reply.deleteLater()
            return
        try:
            data = json.loads(bytes(reply.readAll()))
        except Exception:
            reply.deleteLater()
            return
        reply.deleteLater()
        results = data.get("results", [])
        self._populate_grid(results)

    def _populate_grid(self, results: list) -> None:
        # Clear existing
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        for i, result in enumerate(results):
            media = result.get("media_formats", {})
            tiny = media.get("tinygif", {})
            full = media.get("gif", {})
            thumb_url = tiny.get("url", "")
            gif_url = full.get("url", tiny.get("url", ""))

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
        if url in self._thumb_cache:
            btn.setIcon(QIcon(self._thumb_cache[url]))
            btn.setIconSize(QSize(_THUMB_SIZE - 4, _THUMB_SIZE - 4))
            return
        req = QNetworkRequest(QUrl(url))
        reply = self._nam.get(req)
        reply.finished.connect(
            lambda r=reply, b=btn, u=url: self._on_thumb_loaded(r, b, u)
        )

    def _on_thumb_loaded(
        self, reply: QNetworkReply, btn: QPushButton, url: str
    ) -> None:
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pm = QPixmap()
            pm.loadFromData(reply.readAll())
            if not pm.isNull():
                scaled = pm.scaled(
                    _THUMB_SIZE * 2,
                    _THUMB_SIZE * 2,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                scaled.setDevicePixelRatio(2)
                self._thumb_cache[url] = scaled
                btn.setIcon(QIcon(scaled))
                btn.setIconSize(QSize(_THUMB_SIZE - 4, _THUMB_SIZE - 4))
        reply.deleteLater()

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
