"""Emoji picker popup – browse/search Unicode and custom server emoji."""

from __future__ import annotations

import logging

import sys

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from vox_client.data import emoji_data
from vox_client.state import AppState

log = logging.getLogger(__name__)

_COLS = 8
_CELL = 36
_EMOJI_FONT_PX = 22


def _emoji_font(px: int = _EMOJI_FONT_PX) -> QFont:
    """Return a font that can render color emoji at the given pixel size."""
    if sys.platform == "darwin":
        f = QFont("Apple Color Emoji")
    elif sys.platform == "win32":
        f = QFont("Segoe UI Emoji")
    else:
        f = QFont("Noto Color Emoji")
    f.setPixelSize(px)
    return f


class EmojiPicker(QWidget):
    """Popup grid of emoji with search and category tabs."""

    emoji_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFixedSize(352, 400)
        self.setObjectName("EmojiPicker")

        self._nam = QNetworkAccessManager(self)
        self._pixmap_cache: dict[str, QPixmap] = {}
        self._custom_buttons: list[QPushButton] = []
        self._category_labels: dict[str, QLabel] = {}

        state = AppState.instance()
        c = state.theme.colors

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search emoji\u2026")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search)
        root.addWidget(self._search)

        # Category tab bar
        tab_bar = QWidget()
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(2)
        self._tab_buttons: list[QPushButton] = []
        for cat in emoji_data.CATEGORIES:
            btn = QPushButton(cat[:3])
            btn.setFixedHeight(24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(cat)
            btn.clicked.connect(lambda checked, c=cat: self._scroll_to_category(c))
            tab_layout.addWidget(btn)
            self._tab_buttons.append(btn)
        root.addWidget(tab_bar)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self._scroll, stretch=1)

        self._grid_container = QWidget()
        self._grid_layout = QVBoxLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(2)
        self._scroll.setWidget(self._grid_container)

        self._build_grid()
        self._apply_styles()

        state.emoji_changed.connect(self._rebuild_custom_section)

    def _build_grid(self) -> None:
        """Build the full emoji grid with optional custom section + categories."""
        # Custom emoji section
        self._custom_section = QWidget()
        self._custom_layout = QVBoxLayout(self._custom_section)
        self._custom_layout.setContentsMargins(0, 0, 0, 0)
        self._custom_layout.setSpacing(2)
        self._grid_layout.addWidget(self._custom_section)
        self._rebuild_custom_section()

        # Unicode categories
        cats = emoji_data.by_category()
        for cat in emoji_data.CATEGORIES:
            entries = cats.get(cat, [])
            if not entries:
                continue

            lbl = QLabel(cat)
            lbl.setObjectName("EmojiCatLabel")
            self._category_labels[cat] = lbl
            self._grid_layout.addWidget(lbl)

            grid_w = QWidget()
            grid = QGridLayout(grid_w)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(2)
            for i, entry in enumerate(entries):
                btn = QPushButton(entry.emoji)
                btn.setFixedSize(_CELL, _CELL)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setToolTip(f":{entry.name}:")
                btn.setFont(_emoji_font())
                btn.clicked.connect(lambda checked, e=entry.emoji: self.emoji_selected.emit(e))
                grid.addWidget(btn, i // _COLS, i % _COLS)
            self._grid_layout.addWidget(grid_w)

        self._grid_layout.addStretch()

    def _rebuild_custom_section(self) -> None:
        """Rebuild custom emoji grid from current server state."""
        # Clear old widgets
        while self._custom_layout.count():
            item = self._custom_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._custom_buttons.clear()

        custom = AppState.instance().get_custom_emoji()
        if not custom:
            self._custom_section.hide()
            return
        self._custom_section.show()

        lbl = QLabel("Server")
        lbl.setObjectName("EmojiCatLabel")
        self._custom_layout.addWidget(lbl)

        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(2)

        state = AppState.instance()
        for i, em in enumerate(custom):
            btn = QPushButton()
            btn.setFixedSize(_CELL, _CELL)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f":{em.name}:")
            btn.clicked.connect(lambda checked, n=em.name: self.emoji_selected.emit(f":{n}:"))
            grid.addWidget(btn, i // _COLS, i % _COLS)
            self._custom_buttons.append(btn)

            # Load from local cache first, fall back to network
            local_path = state.get_emoji_image_path(em.name)
            if local_path:
                self._load_local_image(btn, local_path)
            elif em.image:
                self._load_custom_image(btn, state._resolve_image_url(em.image))

        self._custom_layout.addWidget(grid_w)

    def _load_local_image(self, btn: QPushButton, path: str) -> None:
        """Load an emoji image from a local cached file."""
        from PySide6.QtGui import QIcon
        pm = QPixmap(path)
        if not pm.isNull():
            scaled = pm.scaled(
                _EMOJI_FONT_PX * 2, _EMOJI_FONT_PX * 2,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(2)
            btn.setIcon(QIcon(scaled))
            btn.setIconSize(QSize(_EMOJI_FONT_PX, _EMOJI_FONT_PX))

    def _load_custom_image(self, btn: QPushButton, url: str) -> None:
        if url in self._pixmap_cache:
            btn.setIcon(self._pixmap_cache[url])
            btn.setIconSize(QSize(_EMOJI_FONT_PX, _EMOJI_FONT_PX))
            return
        from PySide6.QtCore import QUrl
        req = QNetworkRequest(QUrl(url))
        reply = self._nam.get(req)
        reply.finished.connect(lambda r=reply, b=btn, u=url: self._on_image_loaded(r, b, u))

    def _on_image_loaded(self, reply: QNetworkReply, btn: QPushButton, url: str) -> None:
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pm = QPixmap()
            pm.loadFromData(reply.readAll())
            if not pm.isNull():
                scaled = pm.scaled(
                    _EMOJI_FONT_PX * 2, _EMOJI_FONT_PX * 2,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                scaled.setDevicePixelRatio(2)
                self._pixmap_cache[url] = scaled
                from PySide6.QtGui import QIcon
                btn.setIcon(QIcon(scaled))
                btn.setIconSize(QSize(_EMOJI_FONT_PX, _EMOJI_FONT_PX))
        reply.deleteLater()

    def _on_search(self, text: str) -> None:
        """Filter the grid to show only matching emoji."""
        query = text.strip().lower()
        if not query:
            # Show everything
            for i in range(self._grid_layout.count()):
                item = self._grid_layout.itemAt(i)
                if item and item.widget():
                    item.widget().show()
            self._custom_section.show() if AppState.instance().get_custom_emoji() else self._custom_section.hide()
            return

        # Hide all category sections, show only search results
        for i in range(self._grid_layout.count()):
            item = self._grid_layout.itemAt(i)
            if item and item.widget():
                item.widget().hide()

        # Build a temporary search results section at top
        results = emoji_data.search(query, limit=50)
        # Also search custom emoji
        custom = AppState.instance().get_custom_emoji()
        custom_matches = [e for e in custom if query in e.name.lower()]

        if not results and not custom_matches:
            return

        # Show results in the custom section area (repurpose it)
        self._custom_section.show()
        while self._custom_layout.count():
            item = self._custom_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        lbl = QLabel(f"Results ({len(custom_matches) + len(results)})")
        lbl.setObjectName("EmojiCatLabel")
        self._custom_layout.addWidget(lbl)

        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(2)

        state = AppState.instance()
        idx = 0
        for em in custom_matches:
            btn = QPushButton()
            btn.setFixedSize(_CELL, _CELL)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f":{em.name}:")
            btn.clicked.connect(lambda checked, n=em.name: self.emoji_selected.emit(f":{n}:"))
            grid.addWidget(btn, idx // _COLS, idx % _COLS)
            local_path = state.get_emoji_image_path(em.name)
            if local_path:
                self._load_local_image(btn, local_path)
            elif em.image:
                self._load_custom_image(btn, state._resolve_image_url(em.image))
            idx += 1

        for entry in results:
            btn = QPushButton(entry.emoji)
            btn.setFixedSize(_CELL, _CELL)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f":{entry.name}:")
            font = btn.font()
            font.setPixelSize(_EMOJI_FONT_PX)
            btn.setFont(font)
            btn.clicked.connect(lambda checked, e=entry.emoji: self.emoji_selected.emit(e))
            grid.addWidget(btn, idx // _COLS, idx % _COLS)
            idx += 1

        self._custom_layout.addWidget(grid_w)

    def _scroll_to_category(self, category: str) -> None:
        lbl = self._category_labels.get(category)
        if lbl:
            # Map the label's position to the scroll content widget and scroll
            # so it appears at the top of the viewport.
            pos = lbl.mapTo(self._grid_container, lbl.rect().topLeft())
            self._scroll.verticalScrollBar().setValue(pos.y())

    def show_at(self, global_pos) -> None:
        """Position the picker above the given global point, clamped to screen."""
        from PySide6.QtGui import QGuiApplication

        screen = QGuiApplication.screenAt(global_pos)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()

        x = global_pos.x() - self.width() // 2
        y = global_pos.y() - self.height() - 4

        # Clamp to screen
        x = max(geo.left(), min(x, geo.right() - self.width()))
        y = max(geo.top(), min(y, geo.bottom() - self.height()))

        self.move(x, y)
        self.show()
        self._search.setFocus()
        self._search.clear()

    def restyle(self) -> None:
        self._apply_styles()

    def _apply_styles(self) -> None:
        c = AppState.instance().theme.colors
        self.setStyleSheet(
            f"#EmojiPicker {{ background: {c.bg_panel}; border: 1px solid {c.border}; "
            f"border-radius: 8px; }}"
        )
        self._search.setStyleSheet(
            f"background: {c.bg_input}; color: {c.text_primary}; "
            f"border: 1px solid {c.border}; border-radius: 4px; padding: 6px;"
        )
        tab_ss = (
            f"QPushButton {{ background: transparent; border: none; color: {c.text_dim}; "
            f"font-size: 11px; padding: 2px 6px; border-radius: 3px; }}"
            f"QPushButton:hover {{ background: {c.bg_hover}; color: {c.text_primary}; }}"
        )
        for btn in self._tab_buttons:
            btn.setStyleSheet(tab_ss)
        cell_ss = (
            f"QPushButton {{ background: transparent; border: none; border-radius: 4px; }}"
            f"QPushButton:hover {{ background: {c.bg_hover}; }}"
        )
        ef = _emoji_font()
        self._grid_container.setStyleSheet(
            f"QWidget {{ background: transparent; }}"
            f"QPushButton {{ background: transparent; border: none; border-radius: 4px; "
            f"padding: 0px; "
            f'font-family: "{ef.family()}"; font-size: {_EMOJI_FONT_PX}px; }}'
            f"QPushButton:hover {{ background: {c.bg_hover}; }}"
        )
        cat_label_ss = f"color: {c.text_dim}; font-size: 11px; font-weight: 600; padding: 4px 2px 2px 2px;"
        for lbl in self._category_labels.values():
            lbl.setStyleSheet(cat_label_ss)
