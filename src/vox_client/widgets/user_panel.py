"""User panel – bottom bar of channel sidebar showing current user info and controls."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from vox_client.state import AppState

_ICONS_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"


def _tinted_icon(svg_path: Path, color: str, size: int = 16) -> QIcon:
    """Load an SVG and return a QIcon with paths filled in *color*."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPainter

    svg_text = svg_path.read_text()
    # Inject fill attribute on the root <svg> element
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


class UserPanel(QFrame):
    """Shows avatar, username, status, and control buttons (mute/deafen/settings).

    When not authenticated, shows a clickable "Log In" button instead.
    """

    settings_clicked = pyqtSignal()
    login_clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(52)

        state = AppState.instance()
        c = state.theme.colors

        self.setObjectName("UserPanel")
        self.setStyleSheet(
            f"#UserPanel {{ background-color: {c.bg_deep}; border-top: 1px solid {c.border}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # -- Page 0: Logged-out state ------------------------------------------
        logged_out = QWidget()
        lo_layout = QHBoxLayout(logged_out)
        lo_layout.setContentsMargins(8, 6, 8, 6)
        lo_layout.setSpacing(0)

        self._login_btn = QPushButton("[ LOG IN ]")
        self._login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_btn.setStyleSheet(
            f"QPushButton {{ background-color: transparent; color: {c.accent}; "
            f"border: 1px solid {c.accent_dim}; border-radius: 4px; "
            f"font-size: 11px; font-weight: bold; padding: 6px 0px; }}"
            f"QPushButton:hover {{ background-color: {c.accent_dim}; color: {c.text_primary}; }}"
        )
        self._login_btn.clicked.connect(self.login_clicked.emit)
        lo_layout.addWidget(self._login_btn)

        self._stack.addWidget(logged_out)

        # -- Page 1: Logged-in state -------------------------------------------
        logged_in = QWidget()
        li_layout = QHBoxLayout(logged_in)
        li_layout.setContentsMargins(8, 6, 8, 6)
        li_layout.setSpacing(8)

        # Avatar
        self._avatar = QLabel()
        self._avatar.setFixedSize(28, 28)
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar.setStyleSheet(
            f"background-color: {c.accent_dim}; color: {c.text_primary}; "
            f"border-radius: 14px; font-weight: bold; font-size: 12px;"
        )
        li_layout.addWidget(self._avatar)

        # Name + status
        info = QWidget()
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(0)

        self._name_label = QLabel()
        self._name_label.setStyleSheet(
            f"color: {c.text_primary}; font-size: 11px; font-weight: bold;"
        )
        self._name_label.setMinimumWidth(0)
        info_layout.addWidget(self._name_label)

        self._status_label = QLabel("Online")
        self._status_label.setStyleSheet(f"color: {c.text_dim}; font-size: 10px;")
        self._status_label.setMinimumWidth(0)
        info_layout.addWidget(self._status_label)

        li_layout.addWidget(info, stretch=1)

        # Control buttons (SVG icons from resources/icons/)
        btn_style = (
            f"QPushButton {{ background-color: transparent; "
            f"border: 1px solid {c.border}; border-radius: 3px; padding: 0px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        btn_style_active = (
            f"QPushButton {{ background-color: transparent; "
            f"border: 1px solid {c.border}; border-radius: 3px; padding: 0px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )

        self._muted = False
        self._deafened = False

        self._mute_btn = QPushButton()
        self._mute_btn.setIcon(_tinted_icon(_ICONS_DIR / "microphone.svg", c.text_dim))
        self._mute_btn.setIconSize(QSize(16, 16))
        self._mute_btn.setFixedSize(24, 24)
        self._mute_btn.setToolTip("Mute")
        self._mute_btn.setStyleSheet(btn_style)
        self._mute_btn.clicked.connect(self._toggle_mute)
        li_layout.addWidget(self._mute_btn)

        self._deafen_btn = QPushButton()
        self._deafen_btn.setIcon(_tinted_icon(_ICONS_DIR / "headphones.svg", c.text_dim))
        self._deafen_btn.setIconSize(QSize(16, 16))
        self._deafen_btn.setFixedSize(24, 24)
        self._deafen_btn.setToolTip("Deafen")
        self._deafen_btn.setStyleSheet(btn_style)
        self._deafen_btn.clicked.connect(self._toggle_deafen)
        li_layout.addWidget(self._deafen_btn)

        settings_btn = QPushButton()
        settings_btn.setIcon(_tinted_icon(_ICONS_DIR / "cog.svg", c.text_dim))
        settings_btn.setIconSize(QSize(16, 16))
        settings_btn.setFixedSize(24, 24)
        settings_btn.setToolTip("Settings")
        settings_btn.setStyleSheet(btn_style)
        settings_btn.clicked.connect(self.settings_clicked.emit)
        li_layout.addWidget(settings_btn)

        self._stack.addWidget(logged_in)

        # Start on logged-out page
        self._stack.setCurrentIndex(0)

    def update_user(self) -> None:
        """Refresh display from current state, switching between logged-out/in."""
        state = AppState.instance()
        if state.client is None:
            self._stack.setCurrentIndex(0)
            return

        self._stack.setCurrentIndex(1)
        name = state.get_display_name(state.user_id) if state.user_id else "User"
        self._name_label.setText(name)
        self._avatar.setText(name[0].upper() if name else "?")

        # Update status from presence cache
        status_text = "Online"
        if state.user_id is not None:
            presence = state.get_presence(state.user_id)
            if presence is not None:
                raw = getattr(presence, "status", "online")
                status_map = {
                    "online": "Online",
                    "idle": "Idle",
                    "dnd": "Do Not Disturb",
                    "offline": "Offline",
                }
                status_text = status_map.get(raw, raw.capitalize() if raw else "Online")
        self._status_label.setText(status_text)

    def _toggle_mute(self) -> None:
        self._muted = not self._muted
        state = AppState.instance()
        c = state.theme.colors
        if self._muted:
            self._mute_btn.setIcon(_tinted_icon(_ICONS_DIR / "microphone-off.svg", "#ed4245"))
            self._mute_btn.setToolTip("Unmute")
        else:
            self._mute_btn.setIcon(_tinted_icon(_ICONS_DIR / "microphone.svg", c.text_dim))
            self._mute_btn.setToolTip("Mute")

    def _toggle_deafen(self) -> None:
        self._deafened = not self._deafened
        state = AppState.instance()
        c = state.theme.colors
        if self._deafened:
            self._deafen_btn.setIcon(_tinted_icon(_ICONS_DIR / "headphones-off.svg", "#ed4245"))
            self._deafen_btn.setToolTip("Undeafen")
        else:
            self._deafen_btn.setIcon(_tinted_icon(_ICONS_DIR / "headphones.svg", c.text_dim))
            self._deafen_btn.setToolTip("Deafen")
