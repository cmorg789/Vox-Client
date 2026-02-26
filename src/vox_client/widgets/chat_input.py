"""Chat input – message compose bar with embedded attach button and return hint."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QImage, QKeyEvent, QTextCursor, QTextImageFormat

log = logging.getLogger(__name__)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QWidget

from vox_client._frozen import ICONS_DIR as _ICONS_DIR
from vox_client.state import AppState
from vox_client.widgets.icons import tinted_icon


class _RichInput(QTextEdit):
    """Single-line QTextEdit that can render inline emoji images.

    Exposes a QLineEdit-compatible interface so the emoji completer
    works without modification.
    """

    returnPressed = Signal()
    textChanged_str = Signal(str)  # mirrors QLineEdit.textChanged(str)

    _MAX_HEIGHT = 160
    _SINGLE_LINE = 32

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setTabChangesFocus(True)
        self.setFixedHeight(self._SINGLE_LINE)

        self._placeholder = ""
        super().textChanged.connect(self._relay_text_changed)
        self.document().contentsChanged.connect(self._auto_resize)

    def _relay_text_changed(self) -> None:
        self.textChanged_str.emit(self.text())

    def _auto_resize(self) -> None:
        doc = self.document()
        doc.setTextWidth(self.viewport().width())
        needed = int(doc.size().height()) + 2 * self.frameWidth()
        h = max(self._SINGLE_LINE, min(needed, self._MAX_HEIGHT))
        self.setFixedHeight(h)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if needed > self._MAX_HEIGHT
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

    # -- QLineEdit-compatible API ------------------------------------------

    def text(self) -> str:
        """Return plain text with custom emoji rendered back as :name: shortcodes."""
        doc = self.document()
        result: list[str] = []
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    fmt = frag.charFormat()
                    if fmt.isImageFormat():
                        img_fmt = fmt.toImageFormat()
                        # The image name stores ":emoji_name:"
                        result.append(img_fmt.name())
                    else:
                        result.append(frag.text())
                it += 1
            block = block.next()
        return "".join(result)

    def cursorPosition(self) -> int:  # noqa: N802
        return self.textCursor().position()

    def setCursorPosition(self, pos: int) -> None:  # noqa: N802
        tc = self.textCursor()
        # characterCount() returns UTF-16 code units (same as setPosition),
        # minus 1 for the trailing block separator.  Using len(toPlainText())
        # would count Python code points and clamp incorrectly for non-BMP chars.
        max_pos = self.document().characterCount() - 1
        tc.setPosition(min(pos, max_pos))
        self.setTextCursor(tc)

    def setPlaceholderText(self, text: str) -> None:  # noqa: N802
        self._placeholder = text
        super().setPlaceholderText(text)

    def placeholderText(self) -> str:  # noqa: N802
        return self._placeholder

    def clear(self) -> None:
        super().clear()

    def insert_emoji_image(self, name: str, image_path: str) -> None:
        """Insert a custom emoji as an inline image at the cursor."""
        res_name = f":{name}:"
        img = QImage(image_path)
        if img.isNull():
            # Fallback to text
            self.textCursor().insertText(res_name)
            return
        fm = QFontMetrics(self.font())
        size = fm.height()
        scaled = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        from PySide6.QtCore import QUrl
        self.document().addResource(2, QUrl(res_name), scaled)  # 2 = QTextDocument.ResourceType.ImageResource
        fmt = QTextImageFormat()
        fmt.setName(res_name)
        fmt.setWidth(size)
        fmt.setHeight(size)
        self.textCursor().insertImage(fmt)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self.returnPressed.emit()
                return
        super().keyPressEvent(event)


class ChatInput(QFrame):
    """Bottom input bar: input field with [+] button inside, ↵ hint outside."""

    message_sent = Signal(str)
    typing = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(52)
        self.setMaximumHeight(180)

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

        # Rich text input (borderless, bg matches parent)
        self._input = _RichInput()
        self._input.setPlaceholderText("Message #channel")
        self._input.setStyleSheet(
            f"background: transparent; color: {c.text_primary}; "
            f"border: none; padding: 4px 4px;"
        )
        self._input.returnPressed.connect(self._on_send)
        self._input.textChanged_str.connect(self._on_text_changed)
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
        import re
        # Hide the picker first so the Popup releases focus
        if self._emoji_picker is not None:
            self._emoji_picker.hide()
        # Check if this is a custom emoji shortcode like :name:
        m = re.fullmatch(r":(\w+):", text)
        if m:
            state = AppState.instance()
            local_path = state.get_emoji_image_path(m.group(1))
            if local_path:
                self._input.insert_emoji_image(m.group(1), local_path)
                self._input.setFocus()
                return
        # Unicode emoji or unresolved custom — insert as text
        tc = self._input.textCursor()
        tc.insertText(text)
        self._input.setTextCursor(tc)
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
            f"border: none; padding: 4px 4px;"
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

    def set_dm_name(self, name: str) -> None:
        self._input.setPlaceholderText(f"Message @{name}")

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
