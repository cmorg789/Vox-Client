"""Channel sidebar – 180px panel with server name header and categorized channels."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from vox_sdk.permissions import MANAGE_SERVER, ADMINISTRATOR

from vox_client.state import AppState

_ICONS_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"


def _tinted_icon(svg_path: Path, color: str, size: int = 16) -> QIcon:
    """Load an SVG and return a QIcon with paths filled in *color*."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPainter

    svg_text = svg_path.read_text()
    svg_text = svg_text.replace("<svg ", f'<svg fill="{color}" ', 1)
    renderer = QSvgRenderer(svg_text.encode())
    scale = 2  # render at 2x for HiDPI
    px = size * scale
    pixmap = QPixmap(px, px)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QIcon(pixmap)


class _ChannelItem(QWidget):
    """Single clickable channel entry."""

    clicked = pyqtSignal(int)

    def __init__(self, feed_id: int, name: str, prefix: str = "#", is_voice: bool = False) -> None:
        super().__init__()
        self.feed_id = feed_id
        self._active = False
        self._prefix = prefix
        self._name = name

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(28)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(0)

        self._label = QLabel(f"{prefix}  {name}")
        self._label.setStyleSheet("font-size: 13px;")
        layout.addWidget(self._label)

        self._update_style()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update_style()

    def _update_style(self) -> None:
        state = AppState.instance()
        c = state.theme.colors
        if self._active:
            self.setStyleSheet(
                f"background-color: {c.bg_active}; border-radius: 4px;"
            )
            self._label.setStyleSheet(f"color: {c.accent_bright}; font-size: 13px; font-weight: bold;")
        else:
            self.setStyleSheet("background-color: transparent;")
            self._label.setStyleSheet(f"color: {c.text_secondary}; font-size: 13px;")

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        self.clicked.emit(self.feed_id)

    def enterEvent(self, event) -> None:  # noqa: ANN001
        if not self._active:
            state = AppState.instance()
            c = state.theme.colors
            self.setStyleSheet(f"background-color: {c.bg_hover}; border-radius: 4px;")
            self._label.setStyleSheet(f"color: {c.text_primary}; font-size: 13px;")

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        if not self._active:
            self._update_style()


class ChannelSidebar(QWidget):
    """Categorized channel list with server name header."""

    feed_selected = pyqtSignal(int)
    settings_clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(180)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        state = AppState.instance()
        c = state.theme.colors

        self.setObjectName("ChannelSidebar")
        self.setStyleSheet(f"#ChannelSidebar {{ background-color: {c.bg_panel}; }}")

        # Server name header row
        header_widget = QFrame()
        header_widget.setObjectName("ChannelHeader")
        header_widget.setFixedHeight(40)
        header_widget.setStyleSheet(
            f"#ChannelHeader {{ background-color: {c.bg_panel}; "
            f"border-bottom: 1px solid {c.border}; }}"
        )
        header_row = QHBoxLayout(header_widget)
        header_row.setContentsMargins(12, 0, 8, 0)
        header_row.setSpacing(4)

        self._header = QLabel()
        self._header.setStyleSheet(
            f"color: {c.text_primary}; font-weight: bold; font-size: 13px;"
        )
        header_row.addWidget(self._header, stretch=1)

        self._settings_btn = QPushButton()
        self._settings_btn.setIcon(_tinted_icon(_ICONS_DIR / "cog.svg", c.text_dim))
        self._settings_btn.setIconSize(QSize(14, 14))
        self._settings_btn.setFixedSize(24, 24)
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setStyleSheet(
            f"border: none; padding: 0px; background: transparent;"
        )
        self._settings_btn.clicked.connect(self.settings_clicked)
        self._settings_btn.hide()
        header_row.addWidget(self._settings_btn)

        outer.addWidget(header_widget)

        # Scrollable channel list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"border: none; background-color: {c.bg_panel};")

        self._container = QWidget()
        self._container.setStyleSheet(f"background-color: {c.bg_panel};")
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(4, 8, 4, 8)
        self._list_layout.setSpacing(1)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._container)
        outer.addWidget(scroll, stretch=1)

        self._items: list[_ChannelItem] = []
        self._active_feed_id: int | None = None

    def populate(self) -> None:
        """Build channel list from cached layout data."""
        state = AppState.instance()
        c = state.theme.colors
        layout = state._layout
        if layout is None:
            return

        # Update header
        arrow = "\u25b8"
        self._header.setText(f"{arrow}  {state.server_name}")

        # Show cog if user can manage server
        if state.user_has_permission(MANAGE_SERVER) or state.user_has_permission(ADMINISTRATOR):
            self._settings_btn.show()
        else:
            self._settings_btn.hide()

        # Clear existing items
        for item in self._items:
            item.deleteLater()
        self._items.clear()
        # Clear any remaining category labels
        while self._list_layout.count():
            child = self._list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Group feeds and rooms by category
        cat_feeds: dict[int | None, list] = {}
        cat_rooms: dict[int | None, list] = {}

        for feed in sorted(layout.feeds, key=lambda f: f.name):
            cat_feeds.setdefault(feed.category_id, []).append(feed)

        for room in sorted(layout.rooms, key=lambda r: r.name):
            cat_rooms.setdefault(room.category_id, []).append(room)

        cats = sorted(layout.categories, key=lambda ct: ct.position)

        for cat in cats:
            # Category label
            cat_label = QLabel(cat.name.upper())
            cat_label.setStyleSheet(
                f"color: {c.text_dim}; font-size: 10px; font-weight: bold; "
                f"padding: 12px 12px 4px 12px; letter-spacing: 1px;"
            )
            self._list_layout.addWidget(cat_label)

            feeds = cat_feeds.get(cat.category_id, [])
            for feed in feeds:
                item = _ChannelItem(feed.feed_id, feed.name, prefix="#")
                item.clicked.connect(self._on_channel_clicked)
                self._list_layout.addWidget(item)
                self._items.append(item)

            rooms = cat_rooms.get(cat.category_id, [])
            for room in rooms:
                item = _ChannelItem(room.room_id, room.name, prefix="\u266a", is_voice=True)
                item.clicked.connect(self._on_channel_clicked)
                self._list_layout.addWidget(item)
                self._items.append(item)

        # Uncategorized
        uncategorized_feeds = cat_feeds.get(None, [])
        uncategorized_rooms = cat_rooms.get(None, [])
        if uncategorized_feeds or uncategorized_rooms:
            for feed in uncategorized_feeds:
                item = _ChannelItem(feed.feed_id, feed.name, prefix="#")
                item.clicked.connect(self._on_channel_clicked)
                self._list_layout.addWidget(item)
                self._items.append(item)
            for room in uncategorized_rooms:
                item = _ChannelItem(room.room_id, room.name, prefix="\u266a", is_voice=True)
                item.clicked.connect(self._on_channel_clicked)
                self._list_layout.addWidget(item)
                self._items.append(item)

        self._list_layout.addStretch()

    def _on_channel_clicked(self, feed_id: int) -> None:
        self._active_feed_id = feed_id
        for item in self._items:
            item.set_active(item.feed_id == feed_id)
        self.feed_selected.emit(feed_id)
