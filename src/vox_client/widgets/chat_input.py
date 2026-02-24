"""Chat input – message compose bar with embedded attach button and return hint."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QSize, Qt, pyqtSignal

log = logging.getLogger(__name__)
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from vox_client._frozen import ICONS_DIR as _ICONS_DIR
from vox_client.state import AppState
from vox_client.widgets.icons import tinted_icon


class ChatInput(QFrame):
    """Bottom input bar: input field with [+] button inside, ↵ hint outside."""

    message_sent = pyqtSignal(str)
    typing = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(52)

        state = AppState.instance()
        c = state.theme.colors

        self.setObjectName("ChatInput")
        self.setStyleSheet(
            f"#ChatInput {{ background-color: {c.bg_main}; "
            f"border-top: 1px solid {c.border}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 12)
        layout.setSpacing(4)

        # Composite input: plus button + line edit in a shared border
        field = QWidget()
        field.setObjectName("InputField")
        field.setStyleSheet(
            f"#InputField {{ background-color: {c.bg_input}; "
            f"border: 1px solid {c.border}; border-radius: 4px; }}"
        )
        field_layout = QHBoxLayout(field)
        field_layout.setContentsMargins(4, 0, 4, 0)
        field_layout.setSpacing(0)

        # Plus button inside the field
        self._plus_btn = QPushButton()
        self._plus_btn.setIcon(tinted_icon(_ICONS_DIR / "plus.svg", c.text_secondary))
        self._plus_btn.setIconSize(QSize(14, 14))
        self._plus_btn.setFixedSize(22, 22)
        self._plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plus_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 11px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        field_layout.addWidget(self._plus_btn)

        # Line edit (borderless, bg matches parent)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Message #channel")
        self._input.setStyleSheet(
            f"background: transparent; color: {c.text_primary}; "
            f"border: none; padding: 6px 4px;"
        )
        self._input.returnPressed.connect(self._on_send)
        self._input.textChanged.connect(self._on_text_changed)
        field_layout.addWidget(self._input, stretch=1)

        # Emoji button inside the field (right side)
        self._emoji_btn = QPushButton()
        self._emoji_btn.setIcon(tinted_icon(_ICONS_DIR / "emoticon-outline.svg", c.text_secondary))
        self._emoji_btn.setIconSize(QSize(16, 16))
        self._emoji_btn.setFixedSize(22, 22)
        self._emoji_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._emoji_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 11px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._emoji_btn.clicked.connect(self._on_emoji_btn_clicked)
        field_layout.addWidget(self._emoji_btn)

        layout.addWidget(field, stretch=1)

        # Return hint
        self._hint = QLabel("\u21b5")
        self._hint.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 14px; background: transparent; "
            f"border: none; padding-top: 2px;"
        )
        self._hint.setFixedWidth(20)
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._hint)

        # Lazy-created emoji widgets
        self._emoji_picker = None
        self._emoji_completer = None

        # Create completer immediately so it can monitor typing
        self._ensure_completer()

    def _ensure_picker(self):
        if self._emoji_picker is None:
            from vox_client.widgets.emoji_picker import EmojiPicker

            self._emoji_picker = EmojiPicker()
            self._emoji_picker.emoji_selected.connect(self._insert_emoji_text)

    def _ensure_completer(self):
        if self._emoji_completer is None:
            from vox_client.widgets.emoji_completer import EmojiCompleter

            self._emoji_completer = EmojiCompleter(self._input)
            self._emoji_completer.emoji_selected.connect(lambda _: None)  # insertion handled internally

    def _on_emoji_btn_clicked(self) -> None:
        self._ensure_picker()
        assert self._emoji_picker is not None
        if self._emoji_picker.isVisible():
            self._emoji_picker.hide()
            return
        pos = self._emoji_btn.mapToGlobal(self._emoji_btn.rect().center())
        self._emoji_picker.show_at(pos)

    def _insert_emoji_text(self, text: str) -> None:
        cursor_pos = self._input.cursorPosition()
        current = self._input.text()
        new_text = current[:cursor_pos] + text + current[cursor_pos:]
        self._input.setText(new_text)
        # Qt cursor position counts UTF-16 code units, not Python chars.
        # Encode as UTF-16 (minus BOM) to get the real offset.
        utf16_len = len(text.encode("utf-16-le")) // 2
        self._input.setCursorPosition(cursor_pos + utf16_len)
        self._input.setFocus()

    def restyle(self) -> None:
        """Re-apply inline styles after a theme change."""
        c = AppState.instance().theme.colors
        self.setStyleSheet(
            f"#ChatInput {{ background-color: {c.bg_main}; "
            f"border-top: 1px solid {c.border}; }}"
        )
        field = self.findChild(QWidget, "InputField")
        if field is not None:
            field.setStyleSheet(
                f"#InputField {{ background-color: {c.bg_input}; "
                f"border: 1px solid {c.border}; border-radius: 4px; }}"
            )
        self._plus_btn.setIcon(tinted_icon(_ICONS_DIR / "plus.svg", c.text_secondary))
        self._plus_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 11px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._input.setStyleSheet(
            f"background: transparent; color: {c.text_primary}; "
            f"border: none; padding: 6px 4px;"
        )
        self._emoji_btn.setIcon(tinted_icon(_ICONS_DIR / "emoticon-outline.svg", c.text_secondary))
        self._emoji_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 11px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._hint.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 14px; background: transparent; "
            f"border: none; padding-top: 2px;"
        )
        if self._emoji_picker is not None:
            self._emoji_picker.restyle()
        if self._emoji_completer is not None:
            self._emoji_completer.restyle()

    def set_channel_name(self, name: str) -> None:
        self._input.setPlaceholderText(f"Message #{name}")

    def _on_send(self) -> None:
        text = self._input.text().strip()
        if text:
            self._input.clear()
            self.message_sent.emit(text)

    def _on_text_changed(self) -> None:
        if self._input.text():
            self.typing.emit()

    def focus_input(self) -> None:
        self._input.setFocus()
