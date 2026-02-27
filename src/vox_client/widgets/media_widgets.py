"""Reusable widgets for rendering image/file attachments and embed cards."""

from __future__ import annotations

import logging

from PySide6.QtCore import QBuffer, QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QMovie, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from vox_client.cache import media_cache
from vox_client.state import AppState

log = logging.getLogger(__name__)

# Shared network manager and in-memory pixmap cache (not disk-backed since
# QPixmap isn't serialisable as raw bytes — we go through media_cache for the
# raw data and decode into _pixmap_cache on the fly).
_shared_nam: QNetworkAccessManager | None = None
_pixmap_cache: dict[str, QPixmap] = {}


def _get_nam() -> QNetworkAccessManager:
    global _shared_nam  # noqa: PLW0603
    if _shared_nam is None:
        _shared_nam = QNetworkAccessManager()
    return _shared_nam


def _get(obj: object, attr: str, default: object = None) -> object:
    """Get an attribute from an object or dict."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class AttachmentImageWidget(QLabel):
    """Displays a remote image with async loading and GIF animation."""

    MAX_W, MAX_H = 400, 300

    def __init__(
        self,
        url: str,
        mime: str,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        super().__init__()
        self._url = url
        self._movie_buf: QBuffer | None = None

        # Compute display size
        w = width or self.MAX_W
        h = height or self.MAX_H
        if w > self.MAX_W or h > self.MAX_H:
            ratio = min(self.MAX_W / w, self.MAX_H / h)
            w = int(w * ratio)
            h = int(h * ratio)
        self._display_w = max(w, 32)
        self._display_h = max(h, 32)

        self.setFixedSize(self._display_w, self._display_h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Loading placeholder
        c = AppState.instance().theme.colors
        self.setStyleSheet(
            f"background: {c.bg_input}; border: none; border-radius: 4px;"
        )

        self._fetch()

    def _fetch(self) -> None:
        # In-memory pixmap hit (already decoded)
        if self._url in _pixmap_cache:
            self._apply_pixmap(_pixmap_cache[self._url])
            return
        # Unified cache (memory + disk)
        cached = media_cache.get(self._url)
        if cached is not None:
            self._handle_data(cached)
            return
        # Network fetch
        nam = _get_nam()
        req = QNetworkRequest(QUrl(self._url))
        reply = nam.get(req)
        reply.finished.connect(lambda r=reply: self._on_loaded(r))

    def _on_loaded(self, reply: QNetworkReply) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            log.debug("Image fetch failed: %s %s", self._url, reply.errorString())
            reply.deleteLater()
            return
        data = bytes(reply.readAll())
        reply.deleteLater()
        media_cache.put(self._url, data)
        self._handle_data(data)

    def _handle_data(self, data: bytes) -> None:
        if data[:6] in (b"GIF89a", b"GIF87a"):
            self._apply_gif(data)
        else:
            pm = QPixmap()
            pm.loadFromData(data)
            if not pm.isNull():
                _pixmap_cache[self._url] = pm
                self._apply_pixmap(pm)

    def _apply_gif(self, data: bytes) -> None:
        from PySide6.QtCore import QByteArray
        self._qba = QByteArray(data)
        self._movie_buf = QBuffer(self)
        self._movie_buf.setData(self._qba)
        self._movie_buf.open(QBuffer.OpenModeFlag.ReadOnly)
        self._movie = QMovie(self)
        self._movie.setDevice(self._movie_buf)
        self._movie.setScaledSize(QSize(self._display_w, self._display_h))
        self.setStyleSheet("border: none; border-radius: 4px; background: transparent;")
        self.setMovie(self._movie)
        self._movie.start()

    def _apply_pixmap(self, pm: QPixmap) -> None:
        scaled = pm.scaled(
            self._display_w,
            self._display_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)
        self.setStyleSheet("border: none; border-radius: 4px;")

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        QDesktopServices.openUrl(QUrl(self._url))


class AttachmentFileWidget(QFrame):
    """Displays a non-image file attachment as a clickable card."""

    def __init__(self, name: str, size: int, url: str) -> None:
        super().__init__()
        self._url = url
        c = AppState.instance().theme.colors

        self.setFixedHeight(48)
        self.setMaximumWidth(300)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QFrame {{ background: {c.bg_input}; border: 1px solid {c.border}; "
            f"border-radius: 6px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        icon_lbl = QLabel("\U0001f4ce")
        icon_lbl.setStyleSheet(f"font-size: 18px; border: none;")
        layout.addWidget(icon_lbl)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(0)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color: {c.accent_bright}; font-size: 12px; font-weight: 600; border: none;"
        )
        info.addWidget(name_lbl)
        size_lbl = QLabel(_human_size(size))
        size_lbl.setStyleSheet(f"color: {c.text_dim}; font-size: 10px; border: none;")
        info.addWidget(size_lbl)
        layout.addLayout(info)
        layout.addStretch()

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        QDesktopServices.openUrl(QUrl(self._url))


class EmbedCardWidget(QFrame):
    """Displays a rich embed as a card with colored left border."""

    def __init__(self, embed_data: object) -> None:
        super().__init__()
        c = AppState.instance().theme.colors

        title = _get(embed_data, "title") or ""
        description = _get(embed_data, "description") or ""
        url = _get(embed_data, "url") or ""
        site_name = _get(embed_data, "site_name") or ""
        image = _get(embed_data, "image") or ""
        thumbnail = _get(embed_data, "thumbnail") or ""
        color = _get(embed_data, "color")

        # Colored left border
        if color and isinstance(color, int):
            border_color = f"#{color:06x}"
        else:
            border_color = c.accent

        self.setMaximumWidth(480)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setStyleSheet(
            f"QFrame {{ background: {c.bg_input}; "
            f"border-left: 3px solid {border_color}; "
            f"border-radius: 4px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        if site_name:
            site_lbl = QLabel(site_name)
            site_lbl.setStyleSheet(
                f"color: {c.text_dim}; font-size: 10px; border: none;"
            )
            layout.addWidget(site_lbl)

        if title:
            title_lbl = QLabel(title)
            if url:
                title_lbl.setText(f'<a href="{url}" style="color: {c.accent_bright};">{title}</a>')
                title_lbl.setTextFormat(Qt.TextFormat.RichText)
                title_lbl.setOpenExternalLinks(True)
            else:
                title_lbl.setTextFormat(Qt.TextFormat.PlainText)
            title_lbl.setWordWrap(True)
            title_lbl.setStyleSheet(
                f"color: {c.text_primary}; font-size: 13px; font-weight: 600; border: none;"
            )
            layout.addWidget(title_lbl)

        if description:
            desc_lbl = QLabel(description)
            desc_lbl.setWordWrap(True)
            desc_lbl.setTextFormat(Qt.TextFormat.PlainText)
            desc_lbl.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 12px; border: none;"
            )
            layout.addWidget(desc_lbl)

        # Embed image or thumbnail
        img_url = image or thumbnail
        if img_url:
            state = AppState.instance()
            resolved = state._resolve_image_url(str(img_url))
            img_w = _get(embed_data, "image_width")
            img_h = _get(embed_data, "image_height")
            img_widget = AttachmentImageWidget(
                resolved,
                "image/png",
                width=int(img_w) if img_w else None,
                height=int(img_h) if img_h else None,
            )
            layout.addWidget(img_widget)
