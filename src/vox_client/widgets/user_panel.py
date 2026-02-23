"""User panel – bottom bar of channel sidebar showing current user info and controls."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from vox_client._frozen import ICONS_DIR as _ICONS_DIR
from vox_client.state import AppState
from vox_client.widgets.avatar import AvatarWidget
from vox_client.widgets.icons import tinted_icon


class VoiceStatusBar(QFrame):
    """Compact bar above the user panel showing voice connection status."""

    disconnect_clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(32)
        self.setObjectName("VoiceStatusBar")

        state = AppState.instance()
        c = state.theme.colors

        self.setStyleSheet(
            f"#VoiceStatusBar {{ background-color: {c.bg_deep}; "
            f"border-left: 2px solid {c.status_success}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(6)

        # Connection indicator (headphones icon tinted green)
        self._conn_icon = QLabel()
        self._conn_icon.setPixmap(
            tinted_icon(_ICONS_DIR / "headphones.svg", c.status_success, size=14).pixmap(QSize(14, 14))
        )
        self._conn_icon.setFixedSize(14, 14)
        layout.addWidget(self._conn_icon)

        # Room name
        self._room_label = QLabel()
        self._room_label.setStyleSheet(
            f"color: {c.text_primary}; font-size: 13px; font-weight: 600;"
        )
        layout.addWidget(self._room_label, stretch=1)

        # Disconnect button
        self._disconnect_btn = QPushButton()
        self._disconnect_btn.setIcon(tinted_icon(_ICONS_DIR / "close.svg", c.text_dim, size=12))
        self._disconnect_btn.setIconSize(QSize(12, 12))
        self._disconnect_btn.setFixedSize(20, 20)
        self._disconnect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._disconnect_btn.setToolTip("Disconnect")
        self._disconnect_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 3px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._disconnect_btn.clicked.connect(self.disconnect_clicked.emit)
        layout.addWidget(self._disconnect_btn)

        # Auto-refresh on voice state changes
        state.voice_state_changed.connect(self.refresh)
        self.hide()

    def refresh(self) -> None:
        state = AppState.instance()
        if state.voice_room_id is None:
            self.hide()
            return
        self._room_label.setText(state.get_room_name(state.voice_room_id))
        self.show()

    def restyle(self) -> None:
        c = AppState.instance().theme.colors
        self.setStyleSheet(
            f"#VoiceStatusBar {{ background-color: {c.bg_deep}; "
            f"border-left: 2px solid {c.status_success}; }}"
        )
        self._conn_icon.setPixmap(
            tinted_icon(_ICONS_DIR / "headphones.svg", c.status_success, size=14).pixmap(QSize(14, 14))
        )
        self._room_label.setStyleSheet(
            f"color: {c.text_primary}; font-size: 13px; font-weight: 600;"
        )
        self._disconnect_btn.setIcon(tinted_icon(_ICONS_DIR / "close.svg", c.text_dim, size=12))
        self._disconnect_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 3px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )


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

        # Avatar placeholder (replaced with AvatarWidget in update_user)
        self._avatar = QLabel()
        self._avatar.setFixedSize(28, 28)
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar.setStyleSheet(
            f"background-color: {c.accent_dim}; color: {c.text_primary}; "
            f"border-radius: 14px; font-weight: bold; font-size: 12px;"
        )
        self._li_layout = li_layout
        li_layout.insertWidget(0, self._avatar)

        # Name + status
        info = QWidget()
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(0)

        self._name_label = QLabel()
        self._name_label.setStyleSheet(
            f"color: {c.text_primary}; font-size: 13px; font-weight: 600;"
        )
        self._name_label.setMinimumWidth(0)
        info_layout.addWidget(self._name_label)

        self._status_label = QLabel("Online")
        self._status_label.setStyleSheet(f"color: {c.text_dim}; font-size: 10px;")
        self._status_label.setMinimumWidth(0)
        info_layout.addWidget(self._status_label)

        li_layout.addWidget(info, stretch=1)

        # Control buttons (SVG icons from resources/icons/)
        self._btn_style = (
            f"QPushButton {{ background-color: transparent; "
            f"border: 1px solid {c.border}; border-radius: 3px; padding: 0px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._btn_style_active = (
            f"QPushButton {{ background-color: transparent; "
            f"border: 1px solid {c.accent}; color: {c.accent_bright}; "
            f"border-radius: 3px; padding: 0px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._btn_style_danger = (
            f"QPushButton {{ background-color: transparent; "
            f"border: 1px solid {c.status_danger}; "
            f"border-radius: 3px; padding: 0px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        btn_style = self._btn_style

        self._muted = False
        self._deafened = False

        self._mute_btn = QPushButton()
        self._mute_btn.setIcon(tinted_icon(_ICONS_DIR / "microphone.svg", c.text_dim, size=18))
        self._mute_btn.setIconSize(QSize(18, 18))
        self._mute_btn.setFixedSize(24, 24)
        self._mute_btn.setToolTip("Mute")
        self._mute_btn.setStyleSheet(btn_style)
        self._mute_btn.clicked.connect(self._toggle_mute)
        li_layout.addWidget(self._mute_btn)

        self._deafen_btn = QPushButton()
        self._deafen_btn.setIcon(tinted_icon(_ICONS_DIR / "headphones.svg", c.text_dim, size=18))
        self._deafen_btn.setIconSize(QSize(18, 18))
        self._deafen_btn.setFixedSize(24, 24)
        self._deafen_btn.setToolTip("Deafen")
        self._deafen_btn.setStyleSheet(btn_style)
        self._deafen_btn.clicked.connect(self._toggle_deafen)
        li_layout.addWidget(self._deafen_btn)

        self._settings_btn = QPushButton()
        self._settings_btn.setIcon(tinted_icon(_ICONS_DIR / "cog.svg", c.text_dim, size=18))
        self._settings_btn.setIconSize(QSize(18, 18))
        self._settings_btn.setFixedSize(24, 24)
        self._settings_btn.setToolTip("Settings")
        self._settings_btn.setStyleSheet(btn_style)
        self._settings_btn.clicked.connect(self.settings_clicked.emit)
        li_layout.addWidget(self._settings_btn)

        self._stack.addWidget(logged_in)

        # Start on logged-out page
        self._stack.setCurrentIndex(0)

    def restyle(self) -> None:
        """Re-apply inline styles after a theme change."""
        c = AppState.instance().theme.colors
        self.setStyleSheet(
            f"#UserPanel {{ background-color: {c.bg_deep}; border-top: 1px solid {c.border}; }}"
        )
        # Logged-out button
        self._login_btn.setStyleSheet(
            f"QPushButton {{ background-color: transparent; color: {c.accent}; "
            f"border: 1px solid {c.accent_dim}; border-radius: 4px; "
            f"font-size: 11px; font-weight: bold; padding: 6px 0px; }}"
            f"QPushButton:hover {{ background-color: {c.accent_dim}; color: {c.text_primary}; }}"
        )
        # Logged-in elements
        self._name_label.setStyleSheet(
            f"color: {c.text_primary}; font-size: 13px; font-weight: 600;"
        )
        self._status_label.setStyleSheet(f"color: {c.text_dim}; font-size: 10px;")
        self._btn_style = (
            f"QPushButton {{ background-color: transparent; "
            f"border: 1px solid {c.border}; border-radius: 3px; padding: 0px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._btn_style_active = (
            f"QPushButton {{ background-color: transparent; "
            f"border: 1px solid {c.accent}; color: {c.accent_bright}; "
            f"border-radius: 3px; padding: 0px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._btn_style_danger = (
            f"QPushButton {{ background-color: transparent; "
            f"border: 1px solid {c.status_danger}; "
            f"border-radius: 3px; padding: 0px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        # Re-tint icons and apply correct style based on toggle state
        if self._muted:
            self._mute_btn.setIcon(tinted_icon(_ICONS_DIR / "microphone-off.svg", c.status_danger, size=18))
            self._mute_btn.setStyleSheet(self._btn_style_danger)
        else:
            self._mute_btn.setIcon(tinted_icon(_ICONS_DIR / "microphone.svg", c.text_dim, size=18))
            self._mute_btn.setStyleSheet(self._btn_style)
        if self._deafened:
            self._deafen_btn.setIcon(tinted_icon(_ICONS_DIR / "headphones-off.svg", c.status_danger, size=18))
            self._deafen_btn.setStyleSheet(self._btn_style_danger)
        else:
            self._deafen_btn.setIcon(tinted_icon(_ICONS_DIR / "headphones.svg", c.text_dim, size=18))
            self._deafen_btn.setStyleSheet(self._btn_style)
        self._settings_btn.setIcon(tinted_icon(_ICONS_DIR / "cog.svg", c.text_dim, size=18))
        self._settings_btn.setStyleSheet(self._btn_style)

    def update_user(self) -> None:
        """Refresh display from current state, switching between logged-out/in."""
        state = AppState.instance()
        if state.client is None:
            self._stack.setCurrentIndex(0)
            return

        self._stack.setCurrentIndex(1)
        name = state.get_display_name(state.user_id) if state.user_id else "User"
        self._name_label.setText(name)

        # Replace avatar with AvatarWidget when we have a user_id
        if state.user_id is not None:
            new_avatar = AvatarWidget(state.user_id, size=28)
            self._li_layout.replaceWidget(self._avatar, new_avatar)
            self._avatar.deleteLater()
            self._avatar = new_avatar
        else:
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
        log.debug("Mute toggled: %s", self._muted)
        state = AppState.instance()
        state.voice_set_mute(self._muted)
        c = state.theme.colors
        if self._muted:
            self._mute_btn.setIcon(tinted_icon(_ICONS_DIR / "microphone-off.svg", c.status_danger, size=18))
            self._mute_btn.setStyleSheet(self._btn_style_danger)
            self._mute_btn.setToolTip("Unmute")
        else:
            self._mute_btn.setIcon(tinted_icon(_ICONS_DIR / "microphone.svg", c.text_dim, size=18))
            self._mute_btn.setStyleSheet(self._btn_style)
            self._mute_btn.setToolTip("Mute")

    def _toggle_deafen(self) -> None:
        self._deafened = not self._deafened
        log.debug("Deafen toggled: %s", self._deafened)
        state = AppState.instance()
        state.voice_set_deaf(self._deafened)
        c = state.theme.colors
        if self._deafened:
            self._deafen_btn.setIcon(tinted_icon(_ICONS_DIR / "headphones-off.svg", c.status_danger, size=18))
            self._deafen_btn.setStyleSheet(self._btn_style_danger)
            self._deafen_btn.setToolTip("Undeafen")
        else:
            self._deafen_btn.setIcon(tinted_icon(_ICONS_DIR / "headphones.svg", c.text_dim, size=18))
            self._deafen_btn.setStyleSheet(self._btn_style)
            self._deafen_btn.setToolTip("Deafen")
