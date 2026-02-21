"""Scrollable message list with role-colored authors, date dividers, and basic markdown."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from vox_client.state import AppState


_CODE_RE = re.compile(r"`([^`]+)`")
_MENTION_RE = re.compile(r"@(\w+)")


def _render_body(body: str, accent_bright: str, bg_deep: str, accent_bg: str) -> str:
    """Apply basic markdown formatting to message body.

    Returns HTML-safe text with inline code and @mention highlights.
    """
    import html

    text = html.escape(body)
    # Inline code
    text = _CODE_RE.sub(
        rf'<span style="background-color: {bg_deep}; color: {accent_bright}; '
        rf'padding: 1px 2px; border-radius: 3px; font-size: 12px;">\1</span>',
        text,
    )
    # @mentions — accent_bright text with translucent accent background
    text = _MENTION_RE.sub(
        rf'<span style="color: {accent_bright}; background-color: {accent_bg}; '
        rf'padding: 1px 3px; border-radius: 3px; font-weight: bold;">@\1</span>',
        text,
    )
    return text


class _MessageRow(QWidget):
    """A message row that highlights on hover."""

    def __init__(self, hover_color: str) -> None:
        super().__init__()
        self._hover_color = hover_color
        self._default_style = "background-color: transparent;"
        self.setStyleSheet(self._default_style)

    def enterEvent(self, event) -> None:  # noqa: ANN001
        self.setStyleSheet(f"background-color: {self._hover_color};")

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        self.setStyleSheet(self._default_style)


class MessageList(QScrollArea):
    """Displays messages for the active feed with rich formatting."""

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)

        state = AppState.instance()
        c = state.theme.colors

        self.setStyleSheet(f"background-color: {c.bg_main};")

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout.setContentsMargins(0, 4, 0, 4)
        self._layout.setSpacing(0)
        self.setWidget(self._container)

        self._current_feed_id: int | None = None
        self._last_author: int | None = None
        self._last_date: str | None = None

        # msg_id → body QLabel for edits, msg_id → list of row widgets for deletion
        self._msg_widgets: dict[int, QLabel] = {}
        self._msg_rows: dict[int, list[QWidget]] = {}

        # Live message updates
        state.message_received.connect(self._on_message_received)
        state.message_updated.connect(self._on_message_updated)
        state.message_deleted.connect(self._on_message_deleted)

    async def load_messages(self, feed_id: int) -> None:
        """Fetch and display the most recent messages for *feed_id*."""
        self._current_feed_id = feed_id
        self._last_author = None
        self._last_date = None
        self._clear()

        state = AppState.instance()
        assert state.client is not None
        result = await state.client.messages.list(feed_id, limit=50)

        # Race guard: if user switched channels while awaiting, discard
        if self._current_feed_id != feed_id:
            return

        for msg in result.messages:
            self._add_message(msg.author_id, msg.timestamp, msg.body, msg_id=msg.msg_id)

        self._scroll_to_bottom()

    # -- internal ------------------------------------------------------------

    def _clear(self) -> None:
        self._last_author = None
        self._last_date = None
        self._msg_widgets.clear()
        self._msg_rows.clear()
        while self._layout.count():
            child = self._layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _make_date_divider(self, date_str: str) -> QWidget:
        """Create a date divider with horizontal lines flanking the label."""
        state = AppState.instance()
        c = state.theme.colors

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 8)
        layout.setSpacing(8)

        left_line = QFrame()
        left_line.setFrameShape(QFrame.Shape.HLine)
        left_line.setFixedHeight(1)
        left_line.setStyleSheet(f"background-color: {c.border}; border: none;")
        layout.addWidget(left_line, stretch=1)

        label = QLabel(date_str)
        label.setStyleSheet(f"color: {c.text_dim}; font-size: 11px; padding: 0 8px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        right_line = QFrame()
        right_line.setFrameShape(QFrame.Shape.HLine)
        right_line.setFixedHeight(1)
        right_line.setStyleSheet(f"background-color: {c.border}; border: none;")
        layout.addWidget(right_line, stretch=1)

        return container

    def _add_message(
        self,
        author_id: int | None,
        timestamp: int,
        body: str | None,
        *,
        msg_id: int | None = None,
    ) -> None:
        state = AppState.instance()
        c = state.theme.colors

        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc) if timestamp else None
        time_str = dt.strftime("%H:%M") if dt else ""
        date_str = dt.strftime("%B %-d, %Y") if dt else None

        # Date divider
        if date_str and date_str != self._last_date:
            self._last_date = date_str
            self._layout.addWidget(self._make_date_divider(date_str))

        # System messages (no author)
        if author_id is None:
            sys_msg = QLabel(body or "")
            sys_msg.setWordWrap(True)
            sys_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sys_msg.setStyleSheet(
                f"color: {c.text_dim}; font-style: italic; padding: 4px 16px; font-size: 12px;"
            )
            sys_msg.setTextFormat(Qt.TextFormat.PlainText)
            self._layout.addWidget(sys_msg)
            self._last_author = None
            return

        # Collect row widgets for this message (for deletion tracking)
        row_widgets: list[QWidget] = []

        # Author header (grouped – skip if same author)
        show_header = author_id != self._last_author
        self._last_author = author_id

        if show_header:
            header_row = _MessageRow(c.bg_hover)
            header_layout = QHBoxLayout(header_row)
            header_layout.setContentsMargins(16, 10, 16, 0)
            header_layout.setSpacing(8)

            # Timestamp
            ts_label = QLabel(time_str)
            ts_label.setFixedWidth(48)
            ts_label.setStyleSheet(f"color: {c.text_dim}; font-size: 11px;")
            ts_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            header_layout.addWidget(ts_label)

            # Author name (role-colored)
            author_name = state.get_display_name(author_id)
            role_color = state.get_role_color(author_id) or c.accent
            author_label = QLabel(author_name)
            author_label.setStyleSheet(
                f"color: {role_color}; font-weight: bold; font-size: 13px;"
            )
            header_layout.addWidget(author_label)
            header_layout.addStretch()

            self._layout.addWidget(header_row)
            row_widgets.append(header_row)

        # Message body
        msg_text = body or ""
        msg_row = _MessageRow(c.bg_hover)
        msg_layout = QHBoxLayout(msg_row)
        msg_layout.setContentsMargins(16, 1, 16, 1)
        msg_layout.setSpacing(8)

        # Align with author name (48px timestamp + 8px spacing)
        spacer = QLabel()
        spacer.setFixedWidth(48)
        msg_layout.addWidget(spacer)

        # Translucent accent bg for mentions: pre-blend accent at 15% over bg_main
        from vox_client.theme import hsl_to_hex
        mention_bg = hsl_to_hex(state.theme.hue, 25, 13)
        rendered = _render_body(msg_text, c.accent_bright, c.bg_deep, mention_bg)
        body_label = QLabel(rendered)
        body_label.setWordWrap(True)
        body_label.setStyleSheet(f"color: {c.text_primary}; font-size: 13px; line-height: 1.4;")
        body_label.setTextFormat(Qt.TextFormat.RichText)
        msg_layout.addWidget(body_label, stretch=1)

        self._layout.addWidget(msg_row)
        row_widgets.append(msg_row)

        # Track by msg_id for edit/delete
        if msg_id is not None:
            self._msg_widgets[msg_id] = body_label
            self._msg_rows[msg_id] = row_widgets

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(10, lambda: self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()
        ))

    def _on_message_received(self, event: object) -> None:
        feed_id = getattr(event, "feed_id", None)
        if feed_id != self._current_feed_id:
            return
        self._add_message(
            getattr(event, "author_id", None),
            getattr(event, "timestamp", 0),
            getattr(event, "body", None),
            msg_id=getattr(event, "msg_id", None),
        )
        self._scroll_to_bottom()

    def _on_message_updated(self, event: object) -> None:
        feed_id = getattr(event, "feed_id", None)
        if feed_id != self._current_feed_id:
            return
        msg_id = getattr(event, "msg_id", None)
        if msg_id is None or msg_id not in self._msg_widgets:
            return
        body = getattr(event, "body", None) or ""
        state = AppState.instance()
        c = state.theme.colors
        from vox_client.theme import hsl_to_hex
        mention_bg = hsl_to_hex(state.theme.hue, 25, 13)
        rendered = _render_body(body, c.accent_bright, c.bg_deep, mention_bg)
        edited_tag = (
            f' <span style="color: {c.text_dim}; font-size: 11px;">(edited)</span>'
        )
        self._msg_widgets[msg_id].setText(rendered + edited_tag)

    def _on_message_deleted(self, event: object) -> None:
        feed_id = getattr(event, "feed_id", None)
        if feed_id != self._current_feed_id:
            return
        msg_id = getattr(event, "msg_id", None)
        if msg_id is None or msg_id not in self._msg_rows:
            return
        for widget in self._msg_rows.pop(msg_id):
            self._layout.removeWidget(widget)
            widget.deleteLater()
        self._msg_widgets.pop(msg_id, None)
