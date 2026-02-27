"""Scrollable message list with role-colored authors, date dividers, and basic markdown."""

from __future__ import annotations

import logging
import re
import sys

log = logging.getLogger(__name__)
from datetime import datetime, timezone

# %-d is POSIX-only; Windows uses %#d for no-padding day
_DATE_FMT = "%B %#d, %Y" if sys.platform == "win32" else "%B %-d, %Y"

import shiboken6
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QTextEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from qasync import asyncSlot

from vox_client.state import AppState
from vox_client.widgets.ui_helpers import clear_layout


_CODE_RE = re.compile(r"`([^`]+)`")
_MENTION_RE = re.compile(r"@(\w+)")
_CUSTOM_EMOJI_RE = re.compile(r":(\w+):")
_LONG_WORD_RE = re.compile(r"\S{20,}")
_SENTINEL: object = object()  # default marker for _add_message kwargs


def _render_body(body: str, accent_bright: str, code_color: str, code_bg: str, mention_bg: str) -> str:
    """Apply basic markdown formatting to message body.

    Returns HTML-safe text with inline code, @mention highlights,
    and custom emoji images.
    """
    import html

    text = html.escape(body)
    # Insert zero-width spaces in long unbroken runs so QLabel can wrap them
    text = _LONG_WORD_RE.sub(lambda m: "\u200b".join(m.group()), text)
    # Custom emoji — replace :name: with inline images when cached locally
    state = AppState.instance()

    def _emoji_replace(m: re.Match) -> str:
        name = m.group(1)
        path = state.get_emoji_image_path(name)
        log.debug("Emoji render: :%s: path=%s", name, path)
        if path:
            return (
                f'<img src="file://{path}" width="18" height="18"'
                f' style="vertical-align: middle;">'
            )
        return m.group(0)

    text = _CUSTOM_EMOJI_RE.sub(_emoji_replace, text)
    # Inline code
    text = _CODE_RE.sub(
        rf'<span style="background-color: {code_bg}; color: {code_color}; '
        rf'padding: 1px 2px; border-radius: 3px; font-size: 12px;">\1</span>',
        text,
    )
    # @mentions — accent_bright text with translucent accent background
    text = _MENTION_RE.sub(
        rf'<span style="color: {accent_bright}; background-color: {mention_bg}; '
        rf'padding: 1px 3px; border-radius: 3px; font-weight: bold;">@\1</span>',
        text,
    )
    return text


class _EditTextEdit(QTextEdit):
    """Text editor that emits signals for Enter (submit) and Escape (cancel).

    Shift+Enter inserts a newline; bare Enter submits.
    Accepts only plain text and auto-sizes to fit content.
    """

    cancelled = Signal()
    submitted = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptRichText(False)

    def keyPressEvent(self, event) -> None:  # noqa: ANN001
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.submitted.emit()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: ANN001
        super().focusOutEvent(event)
        self.cancelled.emit()


class _MessageRow(QWidget):
    """A message row that highlights on hover and supports a context menu."""

    def __init__(
        self,
        hover_color: str,
        message_list: MessageList | None = None,
    ) -> None:
        super().__init__()
        self._hover_color = hover_color
        self._default_style = "background-color: transparent;"
        self.setStyleSheet(self._default_style)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._message_list = message_list
        self.msg_id: int | None = None
        self.author_id: int | None = None

    def enterEvent(self, event) -> None:  # noqa: ANN001
        self.setStyleSheet(f"background-color: {self._hover_color};")

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        self.setStyleSheet(self._default_style)

    def contextMenuEvent(self, event) -> None:  # noqa: ANN001
        if self.msg_id is None or self._message_list is None:
            return
        self._message_list._show_context_menu(
            event.globalPos(), self.msg_id, self.author_id,
        )


class MessageList(QScrollArea):
    """Displays messages for the active feed with rich formatting."""

    file_dropped = Signal(str)  # emitted when a file is drag-and-dropped

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)

        state = AppState.instance()
        c = state.theme.colors

        self.setStyleSheet(f"background-color: {c.bg_main};")

        self._container = QWidget()
        self._container.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout.setContentsMargins(0, 4, 0, 4)
        self._layout.setSpacing(0)
        self.setWidget(self._container)

        self._current_feed_id: int | None = None
        self._current_dm_id: int | None = None
        self._last_author: int | None = None
        self._last_date: str | None = None

        # msg_id → body QLabel for edits, msg_id → list of row widgets for deletion
        self._msg_widgets: dict[int, QLabel] = {}
        self._msg_rows: dict[int, list[QWidget]] = {}

        # Context menu / inline edit support
        self._msg_bodies: dict[int, str] = {}          # msg_id → raw body text
        self._msg_authors: dict[int, int | None] = {}  # msg_id → author_id
        self._editing_msg_id: int | None = None

        # Pagination (scroll-up to load older messages)
        self._oldest_msg_id: int | None = None
        self._loading_older: bool = False
        self._has_more: bool = True

        # Live message updates
        state.message_received.connect(self._on_message_received)
        state.message_updated.connect(self._on_message_updated)
        state.message_deleted.connect(self._on_message_deleted)

        # Scroll detection for loading older messages
        self.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)

    def restyle(self) -> None:
        """Re-apply container-level inline styles after a theme change."""
        c = AppState.instance().theme.colors
        self.setStyleSheet(f"background-color: {c.bg_main};")

    # -- drag-and-drop ---------------------------------------------------------

    def dragEnterEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: ANN001, N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.file_dropped.emit(url.toLocalFile())

    async def load_messages(self, feed_id: int) -> None:
        """Fetch and display the most recent messages for *feed_id*."""
        self._current_feed_id = feed_id
        self._current_dm_id = None
        self._last_author = None
        self._last_date = None
        self._clear()

        state = AppState.instance()
        assert state.client is not None
        try:
            result = await state.client.messages.list(feed_id, limit=150)
        except Exception:
            log.error("Failed to load messages for feed %d", feed_id, exc_info=True)
            return

        # Race guard: if user switched channels while awaiting, discard
        if self._current_feed_id != feed_id:
            log.debug("Discarding stale message fetch for feed %d (now on %d)", feed_id, self._current_feed_id)
            return

        self._has_more = len(result.messages) >= 150

        for msg in reversed(result.messages):
            self._add_message(
                msg.author_id, msg.timestamp, msg.body,
                msg_id=msg.msg_id,
                attachments=msg.attachments or None,
                embed=msg.embed,
            )

        # Track oldest message for pagination cursor
        if result.messages:
            # result.messages is newest-first; last element is the oldest
            self._oldest_msg_id = result.messages[-1].msg_id

        self._scroll_to_bottom()

    async def load_dm_messages(self, dm_id: int) -> None:
        """Fetch and display the most recent messages for a DM conversation."""
        self._current_dm_id = dm_id
        self._current_feed_id = None
        self._last_author = None
        self._last_date = None
        self._clear()

        state = AppState.instance()
        assert state.client is not None
        try:
            result = await state.client.dms.list_messages(dm_id, limit=150)
        except Exception:
            log.error("Failed to load DM messages for dm %d", dm_id, exc_info=True)
            return

        # Race guard
        if self._current_dm_id != dm_id:
            return

        self._has_more = len(result.messages) >= 150

        for msg in reversed(result.messages):
            self._add_message(
                msg.author_id, msg.timestamp, msg.body,
                msg_id=msg.msg_id,
                attachments=msg.attachments or None,
                embed=msg.embed,
            )

        if result.messages:
            self._oldest_msg_id = result.messages[-1].msg_id

        self._scroll_to_bottom()

    # -- internal ------------------------------------------------------------

    def _clear(self) -> None:
        self._last_author = None
        self._last_date = None
        self._msg_widgets.clear()
        self._msg_rows.clear()
        self._msg_bodies.clear()
        self._msg_authors.clear()
        self._editing_msg_id = None
        self._oldest_msg_id = None
        self._loading_older = False
        self._has_more = True
        clear_layout(self._layout)

    def _matches_current_context(self, event: object) -> bool:
        """Check if a message event belongs to the currently viewed feed or DM."""
        if self._current_dm_id is not None:
            return getattr(event, "dm_id", None) == self._current_dm_id
        if self._current_feed_id is not None:
            return getattr(event, "feed_id", None) == self._current_feed_id
        return False

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
        insert_idx: int | None = None,
        prev_author: int | None = _SENTINEL,
        prev_date: str | None = _SENTINEL,
        attachments: list | None = None,
        embed: object | None = None,
    ) -> tuple[int | None, int | None, str | None]:
        """Add a message to the layout.

        When *insert_idx* is ``None`` (default), appends to the end using
        ``self._last_author`` / ``self._last_date`` for grouping.  When an
        integer, inserts at that position using the caller-provided
        *prev_author* / *prev_date* instead.

        Returns ``(new_insert_idx, prev_author, prev_date)`` so callers
        that insert in a loop can track state.  For append mode the first
        element is always ``None``.
        """
        state = AppState.instance()
        c = state.theme.colors

        prepend = insert_idx is not None
        cur_author = prev_author if prepend else self._last_author
        cur_date = prev_date if prepend else self._last_date

        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc) if timestamp else None
        time_str = dt.strftime("%H:%M") if dt else ""
        date_str = dt.strftime(_DATE_FMT) if dt else None

        def _place(widget: QWidget) -> None:
            nonlocal insert_idx
            if prepend:
                self._layout.insertWidget(insert_idx, widget)
                insert_idx += 1
            else:
                self._layout.addWidget(widget)

        # Date divider
        if date_str and date_str != cur_date:
            cur_date = date_str
            _place(self._make_date_divider(date_str))

        # System messages (no author)
        if author_id is None:
            sys_msg = QLabel(f"\u2500\u2500 {body or ''} \u2500\u2500")
            sys_msg.setWordWrap(True)
            sys_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sys_msg.setStyleSheet(
                f"color: {c.text_dim}; font-style: italic; padding: 4px 16px; font-size: 12px;"
            )
            sys_msg.setTextFormat(Qt.TextFormat.PlainText)
            _place(sys_msg)
            cur_author = None
            if not prepend:
                self._last_author = None
                self._last_date = cur_date
            return (insert_idx, cur_author, cur_date)

        # Collect row widgets for this message (for deletion tracking)
        row_widgets: list[QWidget] = []

        # Author header (grouped – skip if same author)
        show_header = author_id != cur_author
        cur_author = author_id

        if show_header:
            header_row = _MessageRow(c.bg_hover, message_list=self)
            header_row.msg_id = msg_id
            header_row.author_id = author_id
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
                f"color: {role_color}; font-weight: 600; font-size: 13px;"
            )
            header_layout.addWidget(author_label)
            header_layout.addStretch()

            _place(header_row)
            row_widgets.append(header_row)

        # Message body
        msg_text = body or ""
        msg_row = _MessageRow(c.bg_hover, message_list=self)
        msg_row.msg_id = msg_id
        msg_row.author_id = author_id
        msg_layout = QHBoxLayout(msg_row)
        msg_layout.setContentsMargins(16, 1, 16, 1)
        msg_layout.setSpacing(8)

        # Align with author name (48px timestamp + 8px spacing)
        spacer = QLabel()
        spacer.setFixedWidth(48)
        msg_layout.addWidget(spacer)

        rendered = _render_body(msg_text, c.accent_bright, c.status_success, c.bg_input, c.mention_bg)
        body_label = QLabel(rendered)
        body_label.setWordWrap(True)
        body_label.setMinimumWidth(1)
        body_label.setStyleSheet(f"color: {c.text_primary}; font-size: 13px;")
        body_label.setTextFormat(Qt.TextFormat.RichText)
        msg_layout.addWidget(body_label, stretch=1)

        _place(msg_row)
        row_widgets.append(msg_row)

        # Render attachments
        if attachments:
            from vox_client.widgets.media_widgets import (
                AttachmentFileWidget,
                AttachmentImageWidget,
                _get,
            )

            for att in attachments:
                att_mime = str(_get(att, "mime", "") or "")
                att_url = str(_get(att, "url", "") or "")
                att_name = str(_get(att, "name", "file") or "file")
                att_size = int(_get(att, "size", 0) or 0)
                att_w = _get(att, "width")
                att_h = _get(att, "height")

                if att_url and not att_url.startswith("http"):
                    att_url = state._resolve_image_url(att_url)

                att_row = _MessageRow(c.bg_hover, message_list=self)
                att_row.msg_id = msg_id
                att_row.author_id = author_id
                att_layout = QHBoxLayout(att_row)
                att_layout.setContentsMargins(16, 2, 16, 2)
                att_layout.setSpacing(8)

                att_spacer = QLabel()
                att_spacer.setFixedWidth(48)
                att_layout.addWidget(att_spacer)

                if att_mime.startswith("image/"):
                    widget = AttachmentImageWidget(
                        att_url,
                        att_mime,
                        width=int(att_w) if att_w else None,
                        height=int(att_h) if att_h else None,
                    )
                else:
                    widget = AttachmentFileWidget(att_name, att_size, att_url)
                att_layout.addWidget(widget)
                att_layout.addStretch()

                _place(att_row)
                row_widgets.append(att_row)

        # Render embed
        if embed:
            from vox_client.widgets.media_widgets import EmbedCardWidget

            embed_row = _MessageRow(c.bg_hover, message_list=self)
            embed_row.msg_id = msg_id
            embed_row.author_id = author_id
            embed_layout = QHBoxLayout(embed_row)
            embed_layout.setContentsMargins(16, 4, 16, 4)
            embed_layout.setSpacing(8)

            embed_spacer = QLabel()
            embed_spacer.setFixedWidth(48)
            embed_layout.addWidget(embed_spacer)

            embed_widget = EmbedCardWidget(embed)
            embed_layout.addWidget(embed_widget)
            embed_layout.addStretch()

            _place(embed_row)
            row_widgets.append(embed_row)

        # Track by msg_id for edit/delete
        if msg_id is not None:
            self._msg_widgets[msg_id] = body_label
            self._msg_rows[msg_id] = row_widgets
            self._msg_bodies[msg_id] = msg_text
            self._msg_authors[msg_id] = author_id

        if not prepend:
            self._last_author = author_id
            self._last_date = cur_date

        return (insert_idx, cur_author, cur_date)

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(10, lambda: self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()
        ))

    def _on_message_received(self, event: object) -> None:
        try:
            if not self._matches_current_context(event):
                return
            event_attachments = getattr(event, "attachments", None)
            event_embed = getattr(event, "embed", None)
            self._add_message(
                getattr(event, "author_id", None),
                getattr(event, "timestamp", 0),
                getattr(event, "body", None),
                msg_id=getattr(event, "msg_id", None),
                attachments=event_attachments or None,
                embed=event_embed,
            )
            self._scroll_to_bottom()
        except Exception:
            log.error("Error handling message_received event", exc_info=True)

    def _on_message_updated(self, event: object) -> None:
        try:
            if not self._matches_current_context(event):
                return
            msg_id = getattr(event, "msg_id", None)
            if msg_id is None or msg_id not in self._msg_widgets:
                return
            widget = self._msg_widgets[msg_id]
            if not shiboken6.isValid(widget):
                self._msg_widgets.pop(msg_id, None)
                return
            body = getattr(event, "body", None) or ""
            self._msg_bodies[msg_id] = body
            state = AppState.instance()
            c = state.theme.colors
            rendered = _render_body(body, c.accent_bright, c.status_success, c.bg_input, c.mention_bg)
            edited_tag = (
                f' <span style="color: {c.text_dim}; font-size: 11px;">(edited)</span>'
            )
            widget.setText(rendered + edited_tag)
        except Exception:
            log.error("Error handling message_updated event", exc_info=True)

    def _on_message_deleted(self, event: object) -> None:
        try:
            if not self._matches_current_context(event):
                return
            msg_id = getattr(event, "msg_id", None)
            if msg_id is None or msg_id not in self._msg_rows:
                return
            for widget in self._msg_rows.pop(msg_id):
                if shiboken6.isValid(widget):
                    self._layout.removeWidget(widget)
                    widget.deleteLater()
            self._msg_widgets.pop(msg_id, None)
            self._msg_bodies.pop(msg_id, None)
            self._msg_authors.pop(msg_id, None)
            if msg_id == self._editing_msg_id:
                self._editing_msg_id = None
        except Exception:
            log.error("Error handling message_deleted event", exc_info=True)

    # -- context menu ----------------------------------------------------------

    def _show_context_menu(self, pos, msg_id: int, author_id: int | None) -> None:  # noqa: ANN001
        """Show a right-click context menu for a message."""
        state = AppState.instance()
        c = state.theme.colors

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background-color: {c.bg_panel}; color: {c.text_primary}; "
            f"border: 1px solid {c.border_bright}; border-radius: 4px; padding: 4px; "
            f"font-size: 12px; }}"
            f"QMenu::item {{ padding: 6px 12px; border-radius: 3px; }}"
            f"QMenu::item:selected {{ background-color: {c.bg_active}; }}"
            f"QMenu::separator {{ height: 1px; background: {c.border}; margin: 4px 8px; }}"
        )

        copy_act = menu.addAction("Copy Text")

        is_own = author_id is not None and author_id == state.user_id
        edit_act = None
        delete_act = None
        if is_own:
            menu.addSeparator()
            edit_act = menu.addAction("Edit Message")
            delete_act = menu.addAction("Delete Message")

        action = menu.exec(pos)
        if action is None:
            return
        if action is copy_act:
            self._copy_message(msg_id)
        elif action is edit_act:
            self._start_edit(msg_id)
        elif action is delete_act:
            self._delete_message(msg_id)

    def _copy_message(self, msg_id: int) -> None:
        """Copy the raw message body to the clipboard."""
        body = self._msg_bodies.get(msg_id, "")
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(body)

    # -- inline edit -----------------------------------------------------------

    def _start_edit(self, msg_id: int) -> None:
        """Replace the message body label with an inline line edit."""
        if self._editing_msg_id is not None:
            self._cancel_edit()

        body_label = self._msg_widgets.get(msg_id)
        if body_label is None or not shiboken6.isValid(body_label):
            return

        raw_body = self._msg_bodies.get(msg_id, "")
        state = AppState.instance()
        c = state.theme.colors

        # Find the parent row and its layout
        msg_row = body_label.parent()
        if msg_row is None:
            return
        row_layout = msg_row.layout()
        if row_layout is None:
            return

        body_label.hide()
        self._editing_msg_id = msg_id

        edit_input = _EditTextEdit()
        edit_input.setObjectName("InlineEdit")
        edit_input.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        edit_input.setStyleSheet(
            f"background-color: {c.bg_input}; color: {c.text_primary}; "
            f"border: 1px solid {c.accent_dim}; border-radius: 3px; "
            f"padding: 4px 6px; font-size: 13px;"
        )
        edit_input.setPlainText(raw_body)
        row_layout.insertWidget(row_layout.indexOf(body_label), edit_input, stretch=1)

        # Constrain the row to shrink-wrap the edit input
        msg_row.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        # Auto-size after insertion so word-wrap is calculated at the real width
        def _resize_edit() -> None:
            doc = edit_input.document()
            doc.setTextWidth(edit_input.viewport().width())
            doc_h = doc.size().height()
            margins = edit_input.contentsMargins()
            h = int(doc_h) + margins.top() + margins.bottom() + 2
            h = min(max(h, 32), 160)
            edit_input.setFixedHeight(h)
            msg_row.setFixedHeight(h + 4)

        QTimer.singleShot(0, _resize_edit)
        edit_input.document().contentsChanged.connect(_resize_edit)

        edit_input.setFocus()
        edit_input.selectAll()

        edit_input.submitted.connect(
            lambda: self._finish_edit(msg_id, edit_input.toPlainText()),
        )
        edit_input.cancelled.connect(self._cancel_edit)

    def _cancel_edit(self) -> None:
        """Cancel the current inline edit and restore the body label."""
        msg_id = self._editing_msg_id
        if msg_id is None:
            return
        self._editing_msg_id = None

        body_label = self._msg_widgets.get(msg_id)
        if body_label is not None and shiboken6.isValid(body_label):
            body_label.show()

            msg_row = body_label.parent()
            if msg_row is not None:
                msg_row.setFixedHeight(16777215)  # QWIDGETSIZE_MAX — remove constraint
                msg_row.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
                edit_input = msg_row.findChild(_EditTextEdit, "InlineEdit")
                if edit_input is not None:
                    edit_input.deleteLater()

    @asyncSlot()
    async def _finish_edit(self, msg_id: int, new_text: str) -> None:
        """Save an edited message via the SDK."""
        new_text = new_text.strip()
        if not new_text:
            self._cancel_edit()
            return

        state = AppState.instance()
        if state.client is None:
            self._cancel_edit()
            return

        # Remove the edit widget and restore row layout immediately
        self._editing_msg_id = None
        body_label = self._msg_widgets.get(msg_id)
        if body_label is not None and shiboken6.isValid(body_label):
            msg_row = body_label.parent()
            if msg_row is not None:
                msg_row.setFixedHeight(16777215)
                msg_row.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
                edit_input = msg_row.findChild(_EditTextEdit, "InlineEdit")
                if edit_input is not None:
                    edit_input.deleteLater()

        dm_id = self._current_dm_id
        feed_id = self._current_feed_id
        try:
            if dm_id is not None:
                await state.client.dms.edit_message(dm_id, msg_id, new_text)
            else:
                await state.client.messages.edit(feed_id, msg_id, new_text)
            # The gateway message_update event will refresh the label, but
            # update locally immediately for responsiveness.
            self._msg_bodies[msg_id] = new_text
            if body_label is not None and shiboken6.isValid(body_label):
                c = state.theme.colors
                rendered = _render_body(
                    new_text, c.accent_bright, c.status_success, c.bg_input, c.mention_bg,
                )
                edited_tag = (
                    f' <span style="color: {c.text_dim}; font-size: 11px;">(edited)</span>'
                )
                body_label.setText(rendered + edited_tag)
                body_label.show()
        except Exception:
            log.error("Failed to edit message %d", msg_id, exc_info=True)
            # Restore original text on failure
            if body_label is not None and shiboken6.isValid(body_label):
                body_label.show()

    @asyncSlot()
    async def _delete_message(self, msg_id: int) -> None:
        """Delete a message via the SDK after user confirmation."""
        reply = QMessageBox.question(
            self,
            "Delete Message",
            "Are you sure you want to delete this message?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        state = AppState.instance()
        if state.client is None:
            return
        dm_id = self._current_dm_id
        feed_id = self._current_feed_id
        try:
            if dm_id is not None:
                await state.client.dms.delete_message(dm_id, msg_id)
            else:
                await state.client.messages.delete(feed_id, msg_id)
            # The gateway message_delete event will remove the widgets.
        except Exception:
            log.error("Failed to delete message %d", msg_id, exc_info=True)

    # -- pagination (scroll-up to load older messages) -------------------------

    @asyncSlot(int)
    async def _on_scroll_changed(self, value: int) -> None:
        """Detect when the user scrolls to the top and load older messages."""
        if (
            value == 0
            and not self._loading_older
            and self._has_more
            and (self._current_feed_id is not None or self._current_dm_id is not None)
        ):
            await self._load_older_messages()

    async def _load_older_messages(self) -> None:
        """Fetch and prepend an older page of messages."""
        state = AppState.instance()
        if state.client is None or self._oldest_msg_id is None:
            return

        self._loading_older = True
        feed_id = self._current_feed_id
        dm_id = self._current_dm_id

        try:
            if dm_id is not None:
                result = await state.client.dms.list_messages(
                    dm_id, limit=150, before=self._oldest_msg_id,
                )
            else:
                result = await state.client.messages.list(
                    feed_id, limit=150, before=self._oldest_msg_id,
                )
        except Exception:
            ctx = f"dm {dm_id}" if dm_id else f"feed {feed_id}"
            log.error("Failed to load older messages for %s", ctx, exc_info=True)
            self._loading_older = False
            return

        # Race guard
        if dm_id is not None and self._current_dm_id != dm_id:
            self._loading_older = False
            return
        if dm_id is None and self._current_feed_id != feed_id:
            self._loading_older = False
            return

        if not result.messages:
            self._has_more = False
            self._loading_older = False
            return

        self._has_more = len(result.messages) >= 150

        # Update oldest cursor (messages are newest-first, last is oldest)
        self._oldest_msg_id = result.messages[-1].msg_id

        # Save scroll state so we can restore the viewport position
        scrollbar = self.verticalScrollBar()
        old_max = scrollbar.maximum()
        old_val = scrollbar.value()

        # Prepend older messages in chronological order at the top of the layout
        insert_idx = 0
        prev_author: int | None = None
        prev_date: str | None = None

        for msg in reversed(result.messages):
            insert_idx, prev_author, prev_date = self._add_message(
                msg.author_id,
                msg.timestamp,
                msg.body,
                msg_id=msg.msg_id,
                insert_idx=insert_idx,
                prev_author=prev_author,
                prev_date=prev_date,
                attachments=msg.attachments or None,
                embed=msg.embed,
            )

        # Fix duplicate author header at the pagination boundary:
        # If the last prepended message has the same author as the first
        # existing message, the existing message's header is now redundant.
        if prev_author is not None and insert_idx is not None:
            # The widget right after the prepended block is at index insert_idx
            if insert_idx < self._layout.count():
                boundary_item = self._layout.itemAt(insert_idx)
                if boundary_item is not None:
                    boundary_widget = boundary_item.widget()
                    if (
                        isinstance(boundary_widget, _MessageRow)
                        and boundary_widget.author_id == prev_author
                        and boundary_widget.msg_id is not None
                    ):
                        # This is a header row for the same author — check if
                        # it's actually a header (has author label, not a body row).
                        # Header rows have contentsMargins top=10; body rows top=1.
                        wl = boundary_widget.layout()
                        if wl is not None and wl.contentsMargins().top() == 10:
                            self._layout.removeWidget(boundary_widget)
                            boundary_widget.deleteLater()
                            # Also remove from _msg_rows tracking
                            mid = boundary_widget.msg_id
                            if mid in self._msg_rows and boundary_widget in self._msg_rows[mid]:
                                self._msg_rows[mid].remove(boundary_widget)

        # Restore scroll position so the viewport stays on the same content
        def _restore_scroll() -> None:
            new_max = scrollbar.maximum()
            delta = new_max - old_max
            scrollbar.setValue(old_val + delta)

        QTimer.singleShot(10, _restore_scroll)
        self._loading_older = False
