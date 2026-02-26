"""Server strip – 52px vertical bar with DM button and server icon buttons."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal

log = logging.getLogger(__name__)
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from vox_client._frozen import ICONS_DIR as _ICONS_DIR
from vox_client.state import AppState
from vox_client.widgets.icons import tinted_icon


class _ServerButton(QWidget):
    """36x36 server icon button with a 3x20 accent indicator bar."""

    clicked = pyqtSignal()

    def __init__(self, label: str, server_id: int | None = None) -> None:
        super().__init__()
        self.server_id = server_id
        self._active = False

        self.setFixedSize(52, 36)

        # Indicator bar – positioned absolutely on the left edge
        self._indicator = QLabel(self)
        self._indicator.setFixedSize(3, 20)
        self._indicator.move(0, 8)  # vertically centered in 36px
        self._indicator.hide()

        # The actual button – centered: (52 - 36) / 2 = 8
        self._btn = QPushButton(label, self)
        self._btn.setFixedSize(36, 36)
        self._btn.move(8, 0)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self.clicked.emit)

        self._update_style()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update_style()

    def _update_style(self) -> None:
        state = AppState.instance()
        c = state.theme.colors
        if self._active:
            self._indicator.setStyleSheet(
                f"background-color: {c.accent}; border-radius: 0px;"
                f"border-top-right-radius: 2px; border-bottom-right-radius: 2px;"
            )
            self._indicator.show()
            self._btn.setStyleSheet(
                f"QPushButton {{ background-color: {c.bg_panel}; color: {c.accent_bright}; "
                f"border: 1px solid {c.accent}; border-radius: 6px; font-weight: 600; font-size: 14px; padding: 0px; }}"
            )
        else:
            self._indicator.hide()
            self._btn.setStyleSheet(
                f"QPushButton {{ background-color: {c.bg_panel}; color: {c.text_secondary}; "
                f"border: 1px solid {c.border}; border-radius: 6px; font-size: 14px; padding: 0px; }}"
                f"QPushButton:hover {{ background-color: {c.bg_hover}; color: {c.text_primary}; "
                f"border-color: {c.border_bright}; }}"
            )


class _IconButton(QWidget):
    """36x36 icon-based button with indicator bar, used for the DM button."""

    clicked = pyqtSignal()

    def __init__(self, icon_path: Path) -> None:
        super().__init__()
        self._icon_path = icon_path
        self._active = False

        self.setFixedSize(52, 36)

        self._indicator = QLabel(self)
        self._indicator.setFixedSize(3, 20)
        self._indicator.move(0, 8)
        self._indicator.hide()

        self._btn = QPushButton(self)
        self._btn.setFixedSize(36, 36)
        self._btn.move(8, 0)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self.clicked.emit)

        self._update_style()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update_style()

    def _update_style(self) -> None:
        state = AppState.instance()
        c = state.theme.colors
        icon_color = c.accent_bright if self._active else c.text_secondary
        self._btn.setIcon(tinted_icon(self._icon_path, icon_color, size=20))
        self._btn.setIconSize(QSize(20, 20))
        if self._active:
            self._indicator.setStyleSheet(
                f"background-color: {c.accent}; border-radius: 0px;"
                f"border-top-right-radius: 2px; border-bottom-right-radius: 2px;"
            )
            self._indicator.show()
            self._btn.setStyleSheet(
                f"QPushButton {{ background-color: {c.bg_panel}; "
                f"border: 1px solid {c.accent}; border-radius: 6px; padding: 0px; }}"
            )
        else:
            self._indicator.hide()
            self._btn.setStyleSheet(
                f"QPushButton {{ background-color: {c.bg_panel}; "
                f"border: 1px solid {c.border}; border-radius: 6px; padding: 0px; }}"
                f"QPushButton:hover {{ background-color: {c.bg_hover}; "
                f"border-color: {c.border_bright}; }}"
            )


class ServerStrip(QWidget):
    """Vertical strip of server icons on the far left."""

    server_selected = pyqtSignal(int)
    dm_clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(52)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 8, 0, 8)
        self._layout.setSpacing(8)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._buttons: list[_ServerButton] = []
        self._dm_button: _IconButton | None = None
        self._active_idx = 0
        self._dm_active = False

        state = AppState.instance()
        c = state.theme.colors
        self.setStyleSheet(f"background-color: {c.bg_deep};")

    def restyle(self) -> None:
        """Re-apply container-level inline styles after a theme change."""
        c = AppState.instance().theme.colors
        self.setStyleSheet(f"background-color: {c.bg_deep};")

    def populate(self) -> None:
        """Build the server list from current state."""
        state = AppState.instance()
        c = state.theme.colors

        # Clear existing
        for btn in self._buttons:
            btn.deleteLater()
        self._buttons.clear()
        self._dm_button = None

        # Clear layout (separator, add button, stretch)
        while self._layout.count():
            child = self._layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # DM button at the very top
        dm_btn = _IconButton(_ICONS_DIR / "account-group.svg")
        dm_btn.clicked.connect(self._on_dm_clicked)
        dm_btn.set_active(self._dm_active)
        self._layout.addWidget(dm_btn)
        self._dm_button = dm_btn

        # Separator between DM button and server button
        sep_row1 = QWidget()
        sep_row1.setFixedHeight(2)
        sep_row1_layout = QHBoxLayout(sep_row1)
        sep_row1_layout.setContentsMargins(8, 0, 8, 0)
        sep_row1_layout.setSpacing(0)
        sep1 = QWidget()
        sep1.setFixedHeight(2)
        sep1.setStyleSheet(f"background-color: {c.border};")
        sep_row1_layout.addWidget(sep1)
        self._layout.addWidget(sep_row1)

        # Current server
        name = state.server_name or "S"
        initial = name[0].upper()
        btn = _ServerButton(initial, server_id=0)
        btn.clicked.connect(lambda i=0: self._on_clicked(i))
        self._layout.addWidget(btn)
        self._buttons.append(btn)

        # Spacer line — centered under the button (8px inset each side)
        sep_row = QWidget()
        sep_row.setFixedHeight(2)
        sep_row_layout = QHBoxLayout(sep_row)
        sep_row_layout.setContentsMargins(8, 0, 8, 0)
        sep_row_layout.setSpacing(0)
        sep = QWidget()
        sep.setFixedHeight(2)
        sep.setStyleSheet(f"background-color: {c.border};")
        sep_row_layout.addWidget(sep)
        self._layout.addWidget(sep_row)

        # Add server button — centered like _ServerButton
        add_row = QWidget()
        add_row.setFixedSize(52, 36)
        add_btn = QPushButton(add_row)
        add_btn.setIcon(tinted_icon(_ICONS_DIR / "plus.svg", c.accent, size=18))
        add_btn.setIconSize(QSize(18, 18))
        add_btn.setFixedSize(36, 36)
        add_btn.move(8, 0)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            f"QPushButton {{ background-color: transparent; "
            f"border: 1px dashed {c.accent}; border-radius: 6px; }}"
            f"QPushButton:hover {{ border-color: {c.accent_bright}; }}"
        )
        self._layout.addWidget(add_row)

        self._layout.addStretch()

        # Mark active state
        if self._dm_active:
            for b in self._buttons:
                b.set_active(False)
        elif self._buttons:
            self._buttons[0].set_active(True)

    def _on_clicked(self, idx: int) -> None:
        self._dm_active = False
        if self._dm_button is not None:
            self._dm_button.set_active(False)
        for i, btn in enumerate(self._buttons):
            btn.set_active(i == idx)
        self._active_idx = idx
        state = AppState.instance()
        if state._dm_mode:
            state._dm_mode = False
            state.dm_mode_changed.emit(False)
        if self._buttons[idx].server_id is not None:
            self.server_selected.emit(self._buttons[idx].server_id)

    def _on_dm_clicked(self) -> None:
        self._dm_active = True
        if self._dm_button is not None:
            self._dm_button.set_active(True)
        for btn in self._buttons:
            btn.set_active(False)
        state = AppState.instance()
        if not state._dm_mode:
            state._dm_mode = True
            state.dm_mode_changed.emit(True)
        self.dm_clicked.emit()
