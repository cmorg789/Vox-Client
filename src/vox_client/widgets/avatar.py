"""Reusable circular avatar widget with async image loading."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QUrl
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QLabel

from vox_client.state import AppState

# Shared network manager (one per process is fine for avatar fetches)
_nam: QNetworkAccessManager | None = None


def _shared_nam() -> QNetworkAccessManager:
    global _nam
    if _nam is None:
        _nam = QNetworkAccessManager()
    return _nam


class AvatarWidget(QLabel):
    """Circular avatar that shows a user's image or falls back to their initial.

    Parameters
    ----------
    user_id : int
        The user whose avatar to display.
    size : int
        Diameter in logical pixels (default 24).
    parent : QWidget | None
        Optional parent widget.
    """

    def __init__(self, user_id: int, size: int = 24, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._size = size
        self._user_id = user_id
        self._has_image = False

        state = AppState.instance()
        c = state.theme.colors
        name = state.get_display_name(user_id)
        role_color = state.get_role_color(user_id) or c.accent_dim

        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        radius = size // 2
        font_size = max(size * 2 // 3, 9)
        self.setStyleSheet(
            f"background-color: {role_color}; color: {c.text_primary}; "
            f"border-radius: {radius}px; font-size: {font_size}px; font-weight: 900;"
        )
        self.setText(name[0].upper() if name else "?")

        # Kick off async image load if the member has an avatar URL
        member = state._members.get(user_id)
        if member and member.avatar:
            nam = _shared_nam()
            reply = nam.get(QNetworkRequest(QUrl(member.avatar)))
            reply.finished.connect(lambda r=reply: self._on_reply(r))

    def _on_reply(self, reply: QNetworkReply) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            return
        data = reply.readAll()
        reply.deleteLater()

        src = QPixmap()
        if not src.loadFromData(data):
            return

        self._apply_pixmap(src)

    def _apply_pixmap(self, src: QPixmap) -> None:
        """Scale, center-crop, and clip *src* into a circle."""
        s = self._size * 2  # render at 2× for HiDPI
        scaled = src.scaled(
            s, s,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Center-crop to square
        if scaled.width() != scaled.height():
            d = min(scaled.width(), scaled.height())
            x = (scaled.width() - d) // 2
            y = (scaled.height() - d) // 2
            scaled = scaled.copy(x, y, d, d)

        # Clip to circle
        result = QPixmap(s, s)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, s, s)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()

        result.setDevicePixelRatio(2)
        self.setPixmap(result)
        self.setText("")
        self.setStyleSheet("")  # clear background so the pixmap shows cleanly
        self._has_image = True
