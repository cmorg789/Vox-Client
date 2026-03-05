"""Video grid – displays video tiles for users with cameras enabled."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QWidget

from vox_client.state import AppState


class VideoTile(QWidget):
    """Renders a single user's video frame with username overlay."""

    def __init__(self, user_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.user_id = user_id
        self._frame: QImage | None = None
        self._speaking = False
        self.setMinimumSize(160, 120)

    def set_frame(self, img: QImage) -> None:
        self._frame = img
        self.update()

    def set_speaking(self, speaking: bool) -> None:
        if self._speaking != speaking:
            self._speaking = speaking
            self.update()

    def paintEvent(self, event: object) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        state = AppState.instance()
        c = state.theme.colors

        # Background
        p.fillRect(self.rect(), QColor(c.bg_deep))

        # Draw frame scaled to fit (aspect-ratio-preserving, centered)
        if self._frame is not None and not self._frame.isNull():
            fw, fh = self._frame.width(), self._frame.height()
            ww, wh = self.width(), self.height()
            scale = min(ww / fw, wh / fh)
            dw, dh = int(fw * scale), int(fh * scale)
            x, y = (ww - dw) // 2, (wh - dh) // 2
            p.drawImage(x, y, self._frame.scaled(
                dw, dh, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

        # Speaking border
        if self._speaking:
            pen = QPen(QColor(c.status_success), 2)
            p.setPen(pen)
            p.drawRect(1, 1, self.width() - 2, self.height() - 2)

        # Username overlay (bottom-left)
        name = state.get_display_name(self.user_id) if self.user_id else "You"
        if self.user_id == 0 and state.user_id:
            name = state.get_display_name(state.user_id)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 140))
        font = QFont()
        font.setPixelSize(11)
        p.setFont(font)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(name) + 12
        th = fm.height() + 6
        p.drawRoundedRect(4, self.height() - th - 4, tw, th, 3, 3)
        p.setPen(QColor(255, 255, 255))
        p.drawText(10, self.height() - 4 - 3, name)

        p.end()


class VideoGrid(QWidget):
    """Adaptive grid of VideoTiles for all users with video enabled."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tiles: dict[int, VideoTile] = {}
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(4)

        state = AppState.instance()
        state.video_frame_received.connect(self._on_frame)
        state.video_state_changed.connect(self._on_video_state_changed)
        state.speaking_changed.connect(self._on_speaking_changed)

    def _on_frame(self, user_id: int, img: QImage) -> None:
        tile = self._tiles.get(user_id)
        if tile is not None:
            tile.set_frame(img)

    def _on_video_state_changed(self) -> None:
        state = AppState.instance()
        current_ids = set(self._tiles.keys())
        wanted_ids = set(state._video_users)

        if current_ids == wanted_ids:
            return

        # Remove tiles for users no longer sending video
        for uid in current_ids - wanted_ids:
            tile = self._tiles.pop(uid)
            self._grid.removeWidget(tile)
            tile.deleteLater()

        # Add tiles for new video users
        for uid in wanted_ids - current_ids:
            tile = VideoTile(uid)
            self._tiles[uid] = tile

        self._rebuild()

    def _on_speaking_changed(self, user_id: int, speaking: bool) -> None:
        tile = self._tiles.get(user_id)
        if tile is not None:
            tile.set_speaking(speaking)

    def _rebuild(self) -> None:
        """Clear grid and re-add tiles in an adaptive layout."""
        # Remove all from grid (without deleting)
        for i in reversed(range(self._grid.count())):
            self._grid.takeAt(i)

        n = len(self._tiles)
        if n == 0:
            return

        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)

        uids = sorted(self._tiles.keys())
        for i, uid in enumerate(uids):
            r, col = divmod(i, cols)
            self._grid.addWidget(self._tiles[uid], r, col)

        # Ensure all rows/columns stretch equally
        for r in range(rows):
            self._grid.setRowStretch(r, 1)
        for col in range(cols):
            self._grid.setColumnStretch(col, 1)

    def clear(self) -> None:
        """Remove all tiles (e.g. on voice leave)."""
        for tile in self._tiles.values():
            self._grid.removeWidget(tile)
            tile.deleteLater()
        self._tiles.clear()

    def restyle(self) -> None:
        """Re-apply theme (tiles paint dynamically, nothing to cache)."""
        self.update()
