"""Inline colon-shortcode emoji autocomplete for chat input."""

from __future__ import annotations

import logging
import re

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from vox_client.data import emoji_data
from vox_client.state import AppState

log = logging.getLogger(__name__)

_MAX_RESULTS = 8
_COLON_RE = re.compile(r":(\w{2,})$")


class EmojiCompleter(QWidget):
    """Popup that suggests emoji as the user types :shortcodes."""

    emoji_selected = pyqtSignal(str)  # emits Unicode char or :name: for custom

    def __init__(self, line_edit: QLineEdit, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint,
        )
        self.setObjectName("EmojiCompleter")
        self._line_edit = line_edit
        self._selected = 0
        self._rows: list[_CompletionRow] = []
        self._match_start = 0  # char index where the `:query` starts
        self._nam = QNetworkAccessManager(self)
        self._pixmap_cache: dict[str, QPixmap] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self.hide()

        line_edit.textChanged.connect(self._on_text_changed)
        line_edit.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001
        if obj is not self._line_edit or not self.isVisible():
            return False
        if event.type() != QEvent.Type.KeyPress:
            return False
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.hide()
            return True
        if key == Qt.Key.Key_Down:
            self._move_selection(1)
            return True
        if key == Qt.Key.Key_Up:
            self._move_selection(-1)
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
            if self._rows:
                self._accept_selection()
                return True
        return False

    def _on_text_changed(self, text: str) -> None:
        cursor = self._line_edit.cursorPosition()
        before = text[:cursor]
        m = _COLON_RE.search(before)
        if not m:
            self.hide()
            return

        query = m.group(1).lower()
        self._match_start = m.start()

        # Search custom emoji first, then Unicode
        state = AppState.instance()
        custom = state.get_custom_emoji()
        custom_matches = [e for e in custom if query in e.name.lower()][:_MAX_RESULTS]
        remaining = _MAX_RESULTS - len(custom_matches)
        unicode_matches = emoji_data.search(query, limit=remaining) if remaining > 0 else []

        if not custom_matches and not unicode_matches:
            self.hide()
            return

        self._populate(custom_matches, unicode_matches)
        self._position_popup()
        self.show()

    def _populate(self, custom_matches, unicode_matches) -> None:  # noqa: ANN001
        # Clear existing rows
        layout = self.layout()
        for row in self._rows:
            layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        self._selected = 0

        c = AppState.instance().theme.colors

        for em in custom_matches:
            row = _CompletionRow(
                emoji_text=None,
                label_text=f":{em.name}:",
                is_custom=True,
                value=f":{em.name}:",
                image_url=em.image,
            )
            layout.addWidget(row)
            self._rows.append(row)
            if em.image:
                self._load_image(row, em.image)

        for entry in unicode_matches:
            row = _CompletionRow(
                emoji_text=entry.emoji,
                label_text=f":{entry.name}:",
                is_custom=False,
                value=entry.emoji,
            )
            layout.addWidget(row)
            self._rows.append(row)

        self._update_highlight()
        self._apply_styles()

    def _load_image(self, row: _CompletionRow, url: str) -> None:
        if url in self._pixmap_cache:
            row.set_pixmap(self._pixmap_cache[url])
            return
        req = QNetworkRequest(url)
        reply = self._nam.get(req)
        reply.finished.connect(lambda r=reply, rw=row, u=url: self._on_image_loaded(r, rw, u))

    def _on_image_loaded(self, reply: QNetworkReply, row: _CompletionRow, url: str) -> None:
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pm = QPixmap()
            pm.loadFromData(reply.readAll())
            if not pm.isNull():
                scaled = pm.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self._pixmap_cache[url] = scaled
                row.set_pixmap(scaled)
        reply.deleteLater()

    def _move_selection(self, delta: int) -> None:
        if not self._rows:
            return
        self._selected = (self._selected + delta) % len(self._rows)
        self._update_highlight()

    def _update_highlight(self) -> None:
        c = AppState.instance().theme.colors
        for i, row in enumerate(self._rows):
            if i == self._selected:
                row.setStyleSheet(f"background: {c.bg_active}; border-radius: 4px;")
            else:
                row.setStyleSheet("background: transparent;")

    def _accept_selection(self) -> None:
        if not self._rows:
            return
        row = self._rows[self._selected]
        # Replace :query with the emoji
        text = self._line_edit.text()
        before = text[: self._match_start]
        after = text[self._line_edit.cursorPosition() :]
        new_text = before + row.value + after
        self._line_edit.setText(new_text)
        self._line_edit.setCursorPosition(len(before) + len(row.value))
        self.emoji_selected.emit(row.value)
        self.hide()

    def _position_popup(self) -> None:
        le = self._line_edit
        # Position above the line edit
        global_pos = le.mapToGlobal(QPoint(0, 0))
        self.adjustSize()
        x = global_pos.x()
        y = global_pos.y() - self.sizeHint().height() - 4
        self.move(x, y)

    def restyle(self) -> None:
        self._apply_styles()

    def _apply_styles(self) -> None:
        c = AppState.instance().theme.colors
        self.setStyleSheet(
            f"#EmojiCompleter {{ background: {c.bg_panel}; "
            f"border: 1px solid {c.border}; border-radius: 6px; }}"
        )
        self._update_highlight()


class _CompletionRow(QWidget):
    """Single row: emoji/image + :name: label."""

    def __init__(
        self,
        emoji_text: str | None,
        label_text: str,
        is_custom: bool,
        value: str,
        image_url: str | None = None,
    ) -> None:
        super().__init__()
        self.value = value
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(8)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(20, 20)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if emoji_text:
            font = self._icon_label.font()
            font.setPixelSize(16)
            self._icon_label.setFont(font)
            self._icon_label.setText(emoji_text)
        layout.addWidget(self._icon_label)

        c = AppState.instance().theme.colors
        self._name_label = QLabel(label_text)
        self._name_label.setStyleSheet(f"color: {c.text_primary}; font-size: 12px;")
        layout.addWidget(self._name_label, stretch=1)

    def set_pixmap(self, pm: QPixmap) -> None:
        self._icon_label.setPixmap(pm.scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
