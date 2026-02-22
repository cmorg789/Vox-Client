"""Chat input – message compose bar with embedded attach button and return hint."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

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
        self._plus_btn.setIcon(_tinted_icon(_ICONS_DIR / "plus.svg", c.text_secondary))
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
        self._plus_btn.setIcon(_tinted_icon(_ICONS_DIR / "plus.svg", c.text_secondary))
        self._plus_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 11px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._input.setStyleSheet(
            f"background: transparent; color: {c.text_primary}; "
            f"border: none; padding: 6px 4px;"
        )
        self._hint.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 14px; background: transparent; "
            f"border: none; padding-top: 2px;"
        )

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
