"""User panel – bottom bar of channel sidebar showing current user info and controls."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from vox_client._frozen import ICONS_DIR as _ICONS_DIR
from vox_client.state import AppState
from vox_client.widgets.avatar import AvatarWidget
from vox_client.widgets.icons import tinted_icon


class VoiceStatusBar(QFrame):
    """Compact bar above the user panel showing voice connection status."""

    disconnect_clicked = Signal()

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

        # Camera combo button: icon toggles video, arrow opens settings menu
        self._video_on = False
        self._video_btn = QPushButton()
        self._video_btn.setIcon(tinted_icon(_ICONS_DIR / "video-off.svg", c.text_dim, size=14))
        self._video_btn.setIconSize(QSize(14, 14))
        self._video_btn.setFixedSize(20, 20)
        self._video_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._video_btn.setToolTip("Camera")
        self._btn_style = (
            f"QPushButton {{ background: transparent; border: none; border-radius: 3px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._btn_style_active = (
            f"QPushButton {{ background: transparent; border: 1px solid {c.accent}; border-radius: 3px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._video_btn.setStyleSheet(self._btn_style)
        self._video_btn.clicked.connect(self._toggle_video)
        layout.addWidget(self._video_btn)

        # Dropdown arrow for video settings
        self._video_menu_btn = QPushButton("\u25BE")  # ▾
        self._video_menu_btn.setFixedSize(14, 20)
        self._video_menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._video_menu_btn.setToolTip("Video settings")
        self._video_menu_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; "
            f"color: {c.text_dim}; font-size: 10px; padding: 0px; }}"
            f"QPushButton:hover {{ color: {c.text_primary}; }}"
        )
        self._video_menu_btn.clicked.connect(self._show_video_menu)
        layout.addWidget(self._video_menu_btn)

        # Disconnect button
        self._disconnect_btn = QPushButton()
        self._disconnect_btn.setIcon(tinted_icon(_ICONS_DIR / "close.svg", c.text_dim, size=12))
        self._disconnect_btn.setIconSize(QSize(12, 12))
        self._disconnect_btn.setFixedSize(20, 20)
        self._disconnect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._disconnect_btn.setToolTip("Disconnect")
        self._disconnect_btn.setStyleSheet(self._btn_style)
        self._disconnect_btn.clicked.connect(self.disconnect_clicked.emit)
        layout.addWidget(self._disconnect_btn)

        # Auto-refresh on voice state changes
        state.voice_state_changed.connect(self.refresh)
        state.video_state_changed.connect(self._on_video_state_changed)
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
        self._btn_style = (
            f"QPushButton {{ background: transparent; border: none; border-radius: 3px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._btn_style_active = (
            f"QPushButton {{ background: transparent; border: 1px solid {c.accent}; border-radius: 3px; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._disconnect_btn.setIcon(tinted_icon(_ICONS_DIR / "close.svg", c.text_dim, size=12))
        self._disconnect_btn.setStyleSheet(self._btn_style)
        self._update_video_btn()
        self._video_menu_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; "
            f"color: {c.text_dim}; font-size: 10px; padding: 0px; }}"
            f"QPushButton:hover {{ color: {c.text_primary}; }}"
        )

    # -- video controls --------------------------------------------------------

    def _toggle_video(self) -> None:
        state = AppState.instance()
        state.voice_toggle_video()
        self._video_on = state.voice_self_video
        self._update_video_btn()

    def _on_video_state_changed(self) -> None:
        state = AppState.instance()
        self._video_on = state.voice_self_video if state.voice_room_id else False
        self._update_video_btn()

    def _update_video_btn(self) -> None:
        c = AppState.instance().theme.colors
        if self._video_on:
            self._video_btn.setIcon(tinted_icon(_ICONS_DIR / "video.svg", c.accent, size=14))
            self._video_btn.setStyleSheet(self._btn_style_active)
            self._video_btn.setToolTip("Turn off camera")
        else:
            self._video_btn.setIcon(tinted_icon(_ICONS_DIR / "video-off.svg", c.text_dim, size=14))
            self._video_btn.setStyleSheet(self._btn_style)
            self._video_btn.setToolTip("Camera")

    @staticmethod
    def _load_video_settings() -> tuple[int, int, int, int]:
        """Load saved video settings, returning (width, height, fps, bitrate_kbps)."""
        from PySide6.QtCore import QSettings
        s = QSettings("Vox", "VoxClient")
        w = int(s.value("video/width", 1280))
        h = int(s.value("video/height", 720))
        fps = int(s.value("video/fps", 30))
        kbps = int(s.value("video/bitrate", 1000))
        return w, h, fps, kbps

    @staticmethod
    def _save_video_settings(w: int, h: int, fps: int, kbps: int) -> None:
        from PySide6.QtCore import QSettings
        s = QSettings("Vox", "VoxClient")
        s.setValue("video/width", w)
        s.setValue("video/height", h)
        s.setValue("video/fps", fps)
        s.setValue("video/bitrate", kbps)

    _RES_PRESETS = [
        ("480p", 640, 480),
        ("720p", 1280, 720),
        ("1080p", 1920, 1080),
        ("1440p", 2560, 1440),
        ("4K", 3840, 2160),
        ("Native", 0, 0),
    ]
    _FPS_OPTIONS = [15, 24, 30, 60]
    _BITRATE_OPTIONS = [
        ("Low (250 kbps)", 250),
        ("Medium (500 kbps)", 500),
        ("High (1 Mbps)", 1000),
        ("Very High (2 Mbps)", 2000),
        ("Ultra (4 Mbps)", 4000),
    ]

    def _show_video_menu(self) -> None:
        state = AppState.instance()
        c = state.theme.colors
        saved_w, saved_h, saved_fps, saved_kbps = self._load_video_settings()

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background-color: {c.bg_panel}; color: {c.text_primary}; "
            f"border: 1px solid {c.border_bright}; border-radius: 4px; padding: 4px; "
            f"font-size: 12px; }}"
            f"QMenu::item {{ padding: 6px 12px; border-radius: 3px; }}"
            f"QMenu::item:selected {{ background-color: {c.bg_active}; }}"
        )
        combo_style = (
            f"QComboBox {{ background-color: {c.bg_deep}; color: {c.text_primary}; "
            f"border: 1px solid {c.border}; border-radius: 3px; padding: 3px 6px; "
            f"font-size: 11px; min-width: 120px; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background-color: {c.bg_panel}; "
            f"color: {c.text_primary}; selection-background-color: {c.bg_active}; "
            f"border: 1px solid {c.border_bright}; }}"
        )
        label_style = f"color: {c.text_secondary}; font-size: 11px; border: none;"

        # -- Resolution preset --
        res_widget = QWidget()
        res_widget.setStyleSheet("background: transparent; border: none;")
        rl = QVBoxLayout(res_widget)
        rl.setContentsMargins(8, 4, 8, 4)
        rl.setSpacing(2)
        rl.addWidget(QLabel("Resolution"))
        rl.itemAt(0).widget().setStyleSheet(label_style)

        self._res_combo = QComboBox()
        self._res_combo.setStyleSheet(combo_style)
        selected_res = 0
        for i, (label, w, h) in enumerate(self._RES_PRESETS):
            self._res_combo.addItem(label, (w, h))
            if w == saved_w and h == saved_h:
                selected_res = i
        self._res_combo.setCurrentIndex(selected_res)
        self._res_combo.currentIndexChanged.connect(self._on_setting_changed)
        rl.addWidget(self._res_combo)

        res_action = QWidgetAction(menu)
        res_action.setDefaultWidget(res_widget)
        menu.addAction(res_action)

        # -- FPS --
        fps_widget = QWidget()
        fps_widget.setStyleSheet("background: transparent; border: none;")
        fl = QVBoxLayout(fps_widget)
        fl.setContentsMargins(8, 4, 8, 4)
        fl.setSpacing(2)
        fl.addWidget(QLabel("Frame Rate"))
        fl.itemAt(0).widget().setStyleSheet(label_style)

        self._fps_combo = QComboBox()
        self._fps_combo.setStyleSheet(combo_style)
        selected_fps = 0
        for i, fps in enumerate(self._FPS_OPTIONS):
            self._fps_combo.addItem(f"{fps} fps", fps)
            if fps == saved_fps:
                selected_fps = i
        self._fps_combo.setCurrentIndex(selected_fps)
        self._fps_combo.currentIndexChanged.connect(self._on_setting_changed)
        fl.addWidget(self._fps_combo)

        fps_action = QWidgetAction(menu)
        fps_action.setDefaultWidget(fps_widget)
        menu.addAction(fps_action)

        # -- Bitrate --
        br_widget = QWidget()
        br_widget.setStyleSheet("background: transparent; border: none;")
        bl = QVBoxLayout(br_widget)
        bl.setContentsMargins(8, 4, 8, 4)
        bl.setSpacing(2)
        bl.addWidget(QLabel("Bitrate"))
        bl.itemAt(0).widget().setStyleSheet(label_style)

        self._br_combo = QComboBox()
        self._br_combo.setStyleSheet(combo_style)
        selected_br = 0
        for i, (label, kbps) in enumerate(self._BITRATE_OPTIONS):
            self._br_combo.addItem(label, kbps)
            if kbps == saved_kbps:
                selected_br = i
        self._br_combo.setCurrentIndex(selected_br)
        self._br_combo.currentIndexChanged.connect(self._on_setting_changed)
        bl.addWidget(self._br_combo)

        br_action = QWidgetAction(menu)
        br_action.setDefaultWidget(br_widget)
        menu.addAction(br_action)

        menu.exec(self._video_menu_btn.mapToGlobal(
            self._video_menu_btn.rect().bottomLeft()
        ))

    def _on_setting_changed(self, _index: int) -> None:
        """Save settings and restart video if currently streaming."""
        w, h = self._res_combo.currentData() or (1280, 720)
        fps = self._fps_combo.currentData() or 30
        kbps = self._br_combo.currentData() or 1000
        self._save_video_settings(w, h, fps, kbps)

        state = AppState.instance()
        mc = state._media_client
        if mc is None:
            return
        try:
            mc.set_video_config(w, h, fps, kbps)
            # Restart camera if already streaming so changes take effect
            if state.voice_self_video:
                mc.set_video(False)
                mc.set_video(True)
                log.debug("Video restarted: %dx%d @ %dfps %dkbps", w, h, fps, kbps)
        except Exception:
            log.warning("Failed to apply video config", exc_info=True)


class UserPanel(QFrame):
    """Shows avatar, username, status, and control buttons (mute/deafen/settings).

    When not authenticated, shows a clickable "Log In" button instead.
    """

    settings_clicked = Signal()
    login_clicked = Signal()

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

        # Speaking indicator on avatar
        state.speaking_changed.connect(self._on_speaking_changed)

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

    def _on_speaking_changed(self, user_id: int, speaking: bool) -> None:
        state = AppState.instance()
        if user_id == state.user_id and isinstance(self._avatar, AvatarWidget):
            self._avatar.set_speaking(speaking)

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

