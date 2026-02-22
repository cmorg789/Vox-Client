"""User settings dialog – frameless modal with sidebar navigation."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from qasync import asyncSlot

from vox_sdk.models.enums import DMPermission
from vox_sdk.permissions import CHANGE_NICKNAME

from vox_client.state import AppState, _log_volume
from vox_client.theme import save_flavor
from vox_client.widgets.base_settings_dialog import BaseSettingsDialog
from vox_client.widgets.icons import tinted_icon
from vox_client.widgets.ui_helpers import (
    action_button,
    clear_layout,
    danger_button,
    field_label,
    section_label,
    separator,
    set_status,
    status_label,
)

from vox_client._frozen import ICONS_DIR as _ICONS_DIR


# -- Account Page ------------------------------------------------------------

class _AccountPage(QWidget):
    logout_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        state = AppState.instance()
        c = state.theme.colors

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        row = 0

        # -- Profile section --
        grid.addWidget(section_label("PROFILE"), row, 0, 1, 2)
        row += 1

        # Username (read-only, spans both columns)
        grid.addWidget(field_label("Username"), row, 0, 1, 2)
        row += 1
        self._username_lbl = QLabel("—")
        self._username_lbl.setStyleSheet(
            f"color: {c.text_primary}; font-size: 13px; border: none; padding: 2px 0;"
        )
        grid.addWidget(self._username_lbl, row, 0, 1, 2)
        row += 1

        # Display Name | Nickname
        self._can_change_nick = state.user_has_permission(CHANGE_NICKNAME)
        grid.addWidget(field_label("Display Name"), row, 0)
        grid.addWidget(field_label("Nickname"), row, 1)
        row += 1
        self._display_name_input = QLineEdit()
        self._display_name_input.setPlaceholderText("Display name...")
        grid.addWidget(self._display_name_input, row, 0)
        if self._can_change_nick:
            self._nickname_input = QLineEdit()
            self._nickname_input.setPlaceholderText("Server nickname...")
            grid.addWidget(self._nickname_input, row, 1)
        else:
            self._nickname_input = None
            member = state._members.get(state.user_id) if state.user_id else None
            self._nickname_lbl = QLabel(member.nickname or "—" if member else "—")
            self._nickname_lbl.setStyleSheet(
                f"color: {c.text_primary}; font-size: 13px; border: none; padding: 2px 0;"
            )
            grid.addWidget(self._nickname_lbl, row, 1)
        row += 1

        # Bio | Avatar URL
        grid.addWidget(field_label("Bio"), row, 0)
        grid.addWidget(field_label("Avatar URL"), row, 1)
        row += 1
        self._bio_input = QLineEdit()
        self._bio_input.setPlaceholderText("Tell us about yourself...")
        grid.addWidget(self._bio_input, row, 0)
        self._avatar_input = QLineEdit()
        self._avatar_input.setPlaceholderText("https://example.com/avatar.png")
        grid.addWidget(self._avatar_input, row, 1)
        row += 1

        # Joined info (left) | Save button (right)
        self._info_container = QWidget()
        self._info_container.setStyleSheet("background: transparent;")
        self._info_layout = QVBoxLayout(self._info_container)
        self._info_layout.setContentsMargins(0, 0, 0, 0)
        self._info_layout.setSpacing(2)
        grid.addWidget(self._info_container, row, 0, Qt.AlignmentFlag.AlignTop)

        save_col = QVBoxLayout()
        save_col.setSpacing(2)
        self._status = status_label()
        save_col.addWidget(self._status)
        self._save_btn = action_button("[ SAVE ]")
        self._save_btn.clicked.connect(self._on_save)
        save_col.addWidget(self._save_btn)
        grid.addLayout(save_col, row, 1, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        row += 1

        # Push profile content up, session content down
        grid.setRowStretch(row, 1)
        row += 1

        # -- Separator --
        grid.addWidget(separator(), row, 0, 1, 2)
        row += 1

        # -- Session section --
        grid.addWidget(section_label("SESSION"), row, 0, 1, 2)
        row += 1

        # Server URL (left) | Logout (right)
        grid.addWidget(field_label("Server URL"), row, 0)
        row += 1
        url = ""
        if state.client is not None:
            url = getattr(state.client, "base_url", "") or getattr(state.client.http, "base_url", "")
        url_lbl = QLabel(str(url) or "—")
        url_lbl.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 12px; border: none; padding: 2px 0;"
        )
        url_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(url_lbl, row, 0)
        logout_btn = danger_button("[ LOG OUT ]", width=120)
        logout_btn.clicked.connect(self.logout_requested.emit)
        grid.addWidget(logout_btn, row, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        # Populate inputs from cached member data immediately
        member = state._members.get(state.user_id) if state.user_id else None
        if member:
            self._display_name_input.setText(member.display_name or "")
            if self._nickname_input is not None:
                self._nickname_input.setText(member.nickname or "")

        # Fetch full user profile for username, bio, avatar, etc.
        self._load_profile()

    @asyncSlot()
    async def _load_profile(self) -> None:
        state = AppState.instance()
        if state.client is None or state.user_id is None:
            return
        try:
            user = await state.client.users.get(state.user_id)
        except Exception:
            return

        c = state.theme.colors

        self._username_lbl.setText(user.username)
        # Only overwrite inputs if they're still at their initial (possibly empty) values
        if not self._display_name_input.isModified():
            self._display_name_input.setText(user.display_name or "")
        if not self._bio_input.isModified():
            self._bio_input.setText(user.bio or "")
        if not self._avatar_input.isModified():
            self._avatar_input.setText(user.avatar or "")

        # Read-only info fields
        clear_layout(self._info_layout)

        if user.created_at:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(user.created_at / 1000, tz=timezone.utc)
            self._info_layout.addWidget(field_label("Joined"))
            joined_lbl = QLabel(dt.strftime("%B %-d, %Y"))
            joined_lbl.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 12px; border: none; padding: 2px 0;"
            )
            self._info_layout.addWidget(joined_lbl)

        if user.federated and user.home_domain:
            self._info_layout.addWidget(field_label("Home Domain"))
            domain_lbl = QLabel(user.home_domain)
            domain_lbl.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 12px; border: none; padding: 2px 0;"
            )
            self._info_layout.addWidget(domain_lbl)

    @asyncSlot()
    async def _on_save(self) -> None:
        state = AppState.instance()
        if state.client is None or state.user_id is None:
            return
        self._save_btn.setEnabled(False)
        set_status(self._status, "saving...", "info")
        try:
            display_name = self._display_name_input.text().strip()
            bio = self._bio_input.text().strip()
            avatar = self._avatar_input.text().strip()
            await state.client.users.update_profile(
                state.user_id,
                display_name=display_name,
                bio=bio,
                avatar=avatar,
            )

            if self._nickname_input is not None:
                nickname = self._nickname_input.text().strip()
                result = await state.client.members.update(
                    state.user_id, nickname=nickname,
                )
                state._members[state.user_id] = result

            set_status(self._status, "saved", "success")
        except Exception as exc:
            set_status(self._status, str(exc), "error")
        finally:
            self._save_btn.setEnabled(True)


# -- Appearance Page ---------------------------------------------------------

_FLAVORS = [
    ("mocha", "Mocha", "Dark, warm and cozy"),
    ("macchiato", "Macchiato", "Dark, mid-tone warmth"),
    ("frappe", "Frapp\u00e9", "Dark, muted and soft"),
    ("latte", "Latte", "Light, bright and airy"),
]


class _AppearancePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        state = AppState.instance()
        c = state.theme.colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(section_label("THEME"))

        self._group = QButtonGroup(self)
        self._radios: dict[str, QRadioButton] = {}

        from catppuccin import PALETTE

        for flavor_id, display_name, description in _FLAVORS:
            flavor = getattr(PALETTE, flavor_id)
            fc = flavor.colors

            row = QWidget()
            row.setFixedHeight(48)
            row.setStyleSheet(
                f"background-color: {c.bg_panel}; border: 1px solid {c.border}; "
                f"border-radius: 6px;"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 4, 12, 4)
            row_layout.setSpacing(10)

            rb = QRadioButton()
            rb.setStyleSheet(
                f"QRadioButton {{ border: none; }}"
                f"QRadioButton::indicator {{ width: 14px; height: 14px; "
                f"border: 2px solid {c.text_dim}; border-radius: 9px; background: transparent; }}"
                f"QRadioButton::indicator:checked {{ background-color: {c.accent}; "
                f"border-color: {c.accent_bright}; }}"
            )
            if flavor_id == state.theme.flavor:
                rb.setChecked(True)
            self._group.addButton(rb)
            self._radios[flavor_id] = rb
            row_layout.addWidget(rb)

            # Text column
            text_col = QVBoxLayout()
            text_col.setSpacing(0)
            name_lbl = QLabel(display_name)
            name_lbl.setStyleSheet(
                f"color: {c.text_primary}; font-size: 13px; font-weight: 600; border: none;"
            )
            text_col.addWidget(name_lbl)
            desc_lbl = QLabel(description)
            desc_lbl.setStyleSheet(
                f"color: {c.text_dim}; font-size: 11px; border: none;"
            )
            text_col.addWidget(desc_lbl)
            row_layout.addLayout(text_col, stretch=1)

            # Color swatches
            swatch_row = QHBoxLayout()
            swatch_row.setSpacing(3)
            for swatch_color in (fc.red, fc.peach, fc.yellow, fc.green, fc.blue, fc.mauve):
                dot = QWidget()
                dot.setFixedSize(14, 14)
                dot.setStyleSheet(
                    f"background-color: {swatch_color.hex}; border-radius: 7px; border: none;"
                )
                swatch_row.addWidget(dot)
            row_layout.addLayout(swatch_row)

            layout.addWidget(row)
            layout.addSpacing(4)

        self._group.buttonClicked.connect(self._on_flavor_changed)

        layout.addStretch()

    def _on_flavor_changed(self) -> None:
        state = AppState.instance()
        for flavor_id, rb in self._radios.items():
            if rb.isChecked():
                state.theme.set_flavor(flavor_id)
                save_flavor(flavor_id)
                state.theme_changed.emit()
                break


# -- Mic Sensitivity Slider with live level overlay --------------------------

class _MicSlider(QSlider):
    """Horizontal slider that paints a live mic level behind the groove."""

    _SMOOTH_UP = 0.3
    _SMOOTH_DOWN = 0.08

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._level: float = 0.0

    def set_level(self, raw: float) -> None:
        raw = max(0.0, min(1.0, raw))
        alpha = self._SMOOTH_UP if raw > self._level else self._SMOOTH_DOWN
        self._level += alpha * (raw - self._level)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        c = AppState.instance().theme.colors

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        groove_h = 6
        margin_x = 8
        y = (self.height() - groove_h) // 2
        groove_rect = QRect(margin_x, y, self.width() - 2 * margin_x, groove_h)

        handle_w = 14
        available = groove_rect.width() - handle_w
        val_range = self.maximum() - self.minimum()
        if val_range > 0:
            handle_x = groove_rect.x() + int(available * (self.value() - self.minimum()) / val_range)
        else:
            handle_x = groove_rect.x()
        threshold_x = handle_x + handle_w // 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c.bg_active))
        painter.drawRoundedRect(groove_rect, 3, 3)

        if self._level > 0:
            fill_w = int(groove_rect.width() * self._level)
            threshold = self.value() / 100.0 if self.maximum() > 0 else 0.5
            gate_x = threshold_x - groove_rect.x()

            if self._level >= threshold:
                if gate_x > 0:
                    red_color = QColor(c.status_danger)
                    red_color.setAlpha(120)
                    painter.setBrush(red_color)
                    painter.drawRoundedRect(
                        QRect(groove_rect.x(), groove_rect.y(), gate_x, groove_h), 3, 3,
                    )
                green_w = fill_w - gate_x
                if green_w > 0:
                    green_color = QColor(c.status_success)
                    green_color.setAlpha(160)
                    painter.setBrush(green_color)
                    painter.drawRoundedRect(
                        QRect(groove_rect.x() + gate_x, groove_rect.y(), green_w, groove_h), 3, 3,
                    )
            else:
                clamped = min(fill_w, gate_x)
                if clamped > 0:
                    red_color = QColor(c.status_danger)
                    red_color.setAlpha(120)
                    painter.setBrush(red_color)
                    painter.drawRoundedRect(
                        QRect(groove_rect.x(), groove_rect.y(), clamped, groove_h), 3, 3,
                    )

        handle_y = (self.height() - handle_w) // 2
        painter.setBrush(QColor(c.accent_bright))
        painter.drawEllipse(handle_x, handle_y, handle_w, handle_w)

        painter.end()


# -- Audio & Video Page ------------------------------------------------------

class _AudioVideoPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        from PyQt6.QtCore import QSettings

        c = AppState.instance().theme.colors
        settings = QSettings("Vox", "VoxClient")

        combo_style = (
            f"QComboBox {{ background-color: {c.bg_active}; color: {c.text_primary}; "
            f"border: 1px solid {c.border}; border-radius: 4px; padding: 4px 8px; font-size: 12px; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background-color: {c.bg_panel}; color: {c.text_primary}; "
            f"selection-background-color: {c.bg_active}; border: 1px solid {c.border}; }}"
        )
        test_btn_style = (
            f"QPushButton {{ color: {c.text_dim}; font-size: 11px; "
            f"border: 1px solid {c.border}; border-radius: 4px; "
            f"padding: 4px 10px; background: transparent; }}"
            f"QPushButton:hover {{ color: {c.text_secondary}; "
            f"border-color: {c.accent_dim}; background-color: {c.bg_hover}; }}"
        )

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        row = 0

        self._camera_preview = QLabel("No camera")
        self._camera_preview.setFixedHeight(160)
        self._camera_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._camera_preview.setStyleSheet(
            f"background-color: {c.bg_active}; color: {c.text_dim}; "
            f"font-size: 11px; border: 1px solid {c.border}; border-radius: 4px;"
        )
        grid.addWidget(self._camera_preview, row, 0, 1, 2)
        row += 1

        self._camera = None
        self._capture_session = None
        self._video_sink = None

        grid.addWidget(section_label("CAMERA"), row, 0, 1, 2)
        row += 1
        self._camera_combo = QComboBox()
        self._camera_combo.setFixedHeight(30)
        self._camera_combo.setStyleSheet(combo_style)
        try:
            from PyQt6.QtMultimedia import QMediaDevices
            cameras = QMediaDevices.videoInputs()
            self._camera_combo.addItem("Default", None)
            for dev in cameras:
                self._camera_combo.addItem(dev.description(), dev.id())
            saved = settings.value("av/camera_device")
            if saved:
                idx = self._camera_combo.findData(saved)
                if idx >= 0:
                    self._camera_combo.setCurrentIndex(idx)
        except Exception:
            self._camera_combo.addItem("Default")
        self._camera_combo.currentIndexChanged.connect(self._on_camera_changed)
        grid.addWidget(self._camera_combo, row, 0, 1, 2)
        row += 1

        grid.addWidget(separator(), row, 0, 1, 2)
        row += 1

        grid.addWidget(section_label("INPUT DEVICE"), row, 0)
        grid.addWidget(section_label("OUTPUT DEVICE"), row, 1)
        row += 1

        self._input_combo = QComboBox()
        self._input_combo.setFixedHeight(30)
        self._input_combo.setStyleSheet(combo_style)
        try:
            from PyQt6.QtMultimedia import QMediaDevices
            inputs = QMediaDevices.audioInputs()
            self._input_combo.addItem("Default", None)
            for dev in inputs:
                self._input_combo.addItem(dev.description(), dev.id())
            saved = settings.value("av/input_device")
            if saved:
                idx = self._input_combo.findData(saved)
                if idx >= 0:
                    self._input_combo.setCurrentIndex(idx)
        except Exception:
            self._input_combo.addItem("Default")
        grid.addWidget(self._input_combo, row, 0)

        self._output_combo = QComboBox()
        self._output_combo.setFixedHeight(30)
        self._output_combo.setStyleSheet(combo_style)
        try:
            from PyQt6.QtMultimedia import QMediaDevices
            outputs = QMediaDevices.audioOutputs()
            self._output_combo.addItem("Default", None)
            for dev in outputs:
                self._output_combo.addItem(dev.description(), dev.id())
            saved = settings.value("av/output_device")
            if saved:
                idx = self._output_combo.findData(saved)
                if idx >= 0:
                    self._output_combo.setCurrentIndex(idx)
        except Exception:
            self._output_combo.addItem("Default")
        grid.addWidget(self._output_combo, row, 1)
        row += 1

        grid.addWidget(section_label("INPUT VOLUME"), row, 0)
        grid.addWidget(section_label("OUTPUT VOLUME"), row, 1)
        row += 1

        saved_input_vol = settings.value("av/input_volume", 100, type=int)
        saved_output_vol = settings.value("av/output_volume", 100, type=int)

        input_vol_row = QWidget()
        input_vol_row.setStyleSheet("background: transparent; border: none;")
        iv_layout = QHBoxLayout(input_vol_row)
        iv_layout.setContentsMargins(0, 0, 0, 0)
        iv_layout.setSpacing(8)
        self._input_vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._input_vol_slider.setRange(0, 200)
        self._input_vol_slider.setValue(saved_input_vol)
        iv_layout.addWidget(self._input_vol_slider, stretch=1)
        self._input_vol_label = QLabel(f"{saved_input_vol}%")
        self._input_vol_label.setFixedWidth(36)
        self._input_vol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._input_vol_label.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 11px; border: none;"
        )
        iv_layout.addWidget(self._input_vol_label)
        grid.addWidget(input_vol_row, row, 0)

        output_vol_row = QWidget()
        output_vol_row.setStyleSheet("background: transparent; border: none;")
        ov_layout = QHBoxLayout(output_vol_row)
        ov_layout.setContentsMargins(0, 0, 0, 0)
        ov_layout.setSpacing(8)
        self._output_vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._output_vol_slider.setRange(0, 200)
        self._output_vol_slider.setValue(saved_output_vol)
        ov_layout.addWidget(self._output_vol_slider, stretch=1)
        self._output_vol_label = QLabel(f"{saved_output_vol}%")
        self._output_vol_label.setFixedWidth(36)
        self._output_vol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._output_vol_label.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 11px; border: none;"
        )
        ov_layout.addWidget(self._output_vol_label)
        grid.addWidget(output_vol_row, row, 1)

        self._input_vol_slider.valueChanged.connect(self._on_input_vol_changed)
        self._output_vol_slider.valueChanged.connect(self._on_output_vol_changed)
        row += 1

        grid.addWidget(section_label("NOISE GATE"), row, 0)
        row += 1

        self._mic_slider = _MicSlider()
        self._mic_slider.setRange(0, 100)
        saved_gate = settings.value("av/noise_gate", 30, type=int)
        self._mic_slider.setValue(saved_gate)
        self._mic_slider.setFixedHeight(28)
        self._mic_slider.setStyleSheet("background: transparent; border: none;")
        grid.addWidget(self._mic_slider, row, 0)

        self._speaker_test_btn = QPushButton("Test Speakers")
        self._speaker_test_btn.setFixedHeight(28)
        self._speaker_test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._speaker_test_btn.setStyleSheet(test_btn_style)
        self._speaker_test_btn.clicked.connect(self._on_test_speakers)
        grid.addWidget(self._speaker_test_btn, row, 1)
        row += 1

        self._audio_source = None

        grid.addWidget(separator(), row, 0, 1, 2)
        row += 1

        self._status = status_label()
        grid.addWidget(self._status, row, 0)
        save_btn = action_button("[ SAVE ]")
        save_btn.clicked.connect(self._on_save)
        grid.addWidget(save_btn, row, 1, Qt.AlignmentFlag.AlignRight)
        row += 1

        grid.setRowStretch(row, 1)

    def _on_input_vol_changed(self, value: int) -> None:
        self._input_vol_label.setText(f"{value}%")
        if self._audio_source is not None:
            self._audio_source.setVolume(_log_volume(value))

    def _on_output_vol_changed(self, value: int) -> None:
        self._output_vol_label.setText(f"{value}%")

    @staticmethod
    def _request_av_permission(
        media_type: str, callback: callable, denied_callback: callable,
    ) -> None:
        try:
            from PyQt6.QtWidgets import QApplication
            if media_type == "vide":
                from PyQt6.QtCore import QCameraPermission
                perm = QCameraPermission()
            else:
                from PyQt6.QtCore import QMicrophonePermission
                perm = QMicrophonePermission()
            qapp = QApplication.instance()
            from PyQt6.QtCore import Qt as QtNS
            status = qapp.checkPermission(perm)
            if status == QtNS.PermissionStatus.Granted:
                callback()
                return
        except Exception:
            pass

        if sys.platform == "darwin":
            try:
                import AVFoundation as AVF
                av_status = AVF.AVCaptureDevice.authorizationStatusForMediaType_(media_type)
                if av_status == 3:
                    callback()
                elif av_status == 0:
                    def _handler(granted: bool) -> None:
                        from PyQt6.QtCore import QTimer
                        target = callback if granted else denied_callback
                        QTimer.singleShot(0, target)
                    AVF.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                        media_type, _handler,
                    )
                else:
                    denied_callback()
                return
            except ImportError:
                pass

        callback()

    def _on_camera_changed(self) -> None:
        if self._camera is not None:
            self._stop_camera()
            self._request_av_permission(
                "vide", self._start_camera, self._on_camera_denied,
            )

    def _on_camera_denied(self) -> None:
        if sys.platform == "darwin":
            self._camera_preview.setText(
                "Camera access denied\nGrant access in System Settings\n→ Privacy & Security → Camera"
            )
        else:
            self._camera_preview.setText("Camera access denied")

    def _start_camera(self) -> None:
        try:
            from PyQt6.QtMultimedia import QCamera, QMediaCaptureSession, QVideoSink

            dev_data = self._camera_combo.currentData()
            if dev_data is not None:
                from PyQt6.QtMultimedia import QMediaDevices
                for d in QMediaDevices.videoInputs():
                    if d.id() == dev_data:
                        self._camera = QCamera(d)
                        break
                else:
                    self._camera = QCamera()
            else:
                self._camera = QCamera()

            self._video_sink = QVideoSink(self)
            self._capture_session = QMediaCaptureSession(self)
            self._capture_session.setCamera(self._camera)
            self._capture_session.setVideoSink(self._video_sink)
            self._video_sink.videoFrameChanged.connect(self._on_video_frame)
            self._camera.errorOccurred.connect(self._on_camera_error)
            self._camera.start()
            self._camera_preview.setText("Starting camera...")
        except Exception:
            self._camera_preview.setText("Camera unavailable")

    def _on_camera_error(self, error, description: str) -> None:  # noqa: ANN001
        msg = description or "Camera error"
        if sys.platform == "darwin":
            msg += "\nGrant camera access in System Settings\n→ Privacy & Security → Camera"
        self._camera_preview.setText(msg)

    def _on_video_frame(self, frame) -> None:  # noqa: ANN001
        if frame.isValid():
            scale = 2
            target = QSize(
                self._camera_preview.width() * scale,
                self._camera_preview.height() * scale,
            )
            image = frame.toImage().scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            pixmap = QPixmap.fromImage(image)
            pixmap.setDevicePixelRatio(scale)
            self._camera_preview.setPixmap(pixmap)

    def _stop_camera(self) -> None:
        if self._camera is not None:
            self._camera.stop()
            self._camera = None
        self._capture_session = None
        self._video_sink = None
        self._camera_preview.clear()
        self._camera_preview.setText("No camera")

    def _on_mic_denied(self) -> None:
        if sys.platform == "darwin":
            set_status(
                self._status,
                "Mic access denied — grant access in System Settings → Privacy & Security → Microphone",
                "error",
            )
        else:
            set_status(self._status, "Microphone access denied", "error")

    def _start_mic_capture(self) -> None:
        try:
            from PyQt6.QtMultimedia import QAudioSource, QMediaDevices

            dev_data = self._input_combo.currentData()
            dev = QMediaDevices.defaultAudioInput()
            if dev_data is not None:
                for d in QMediaDevices.audioInputs():
                    if d.id() == dev_data:
                        dev = d
                        break

            fmt = dev.preferredFormat()
            self._mic_sample_format = fmt.sampleFormat()

            self._audio_source = QAudioSource(dev, fmt, self)
            self._audio_source.setVolume(_log_volume(self._input_vol_slider.value()))
            self._audio_io = self._audio_source.start()
            self._audio_io.readyRead.connect(self._on_mic_data)
        except Exception:
            pass

    def _on_mic_data(self) -> None:
        if self._audio_io is None:
            return
        data = self._audio_io.readAll()
        if len(data) < 4:
            return
        import math, struct
        from PyQt6.QtMultimedia import QAudioFormat
        raw = bytes(data.data())
        if self._mic_sample_format == QAudioFormat.SampleFormat.Float:
            n = len(raw) // 4
            samples = struct.unpack(f"<{n}f", raw[:n * 4])
            peak = max(abs(s) for s in samples) if samples else 0.0
        else:
            n = len(raw) // 2
            samples = struct.unpack(f"<{n}h", raw[:n * 2])
            peak = (max(abs(s) for s in samples) if samples else 0) / 32768.0

        if peak > 1e-6:
            db = 20 * math.log10(peak)
            level = max(0.0, min(1.0, (db + 60) / 60))
        else:
            level = 0.0
        self._mic_slider.set_level(level)

    def _stop_mic_capture(self) -> None:
        if self._audio_source is not None:
            self._audio_source.stop()
            self._audio_source = None
        self._mic_slider.set_level(0.0)

    def _on_test_speakers(self) -> None:
        try:
            from PyQt6.QtMultimedia import QAudioSink, QAudioFormat, QMediaDevices
            from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QTimer
            import math, struct

            fmt = QAudioFormat()
            fmt.setSampleRate(44100)
            fmt.setChannelCount(2)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

            dev_data = self._output_combo.currentData()
            dev = QMediaDevices.defaultAudioOutput()
            if dev_data is not None:
                for d in QMediaDevices.audioOutputs():
                    if d.id() == dev_data:
                        dev = d
                        break

            rate = 44100
            dur = 0.4
            n = int(rate * dur)
            amplitude = 16000

            left_samples = bytearray()
            for i in range(n):
                s = int(amplitude * math.sin(2 * math.pi * 440 * i / rate))
                left_samples += struct.pack("<hh", s, 0)

            right_samples = bytearray()
            for i in range(n):
                s = int(amplitude * math.sin(2 * math.pi * 440 * i / rate))
                right_samples += struct.pack("<hh", 0, s)

            gap = 0.15
            gap_samples = b"\x00" * (int(rate * gap) * 4)
            raw = bytes(left_samples) + gap_samples + bytes(right_samples)
            total_duration = dur * 2 + gap

            buf = QBuffer(self)
            buf.setData(QByteArray(raw))
            buf.open(QIODevice.OpenModeFlag.ReadOnly)

            sink = QAudioSink(dev, fmt, self)
            sink.setVolume(_log_volume(self._output_vol_slider.value()))
            sink.start(buf)

            self._speaker_test_btn.setEnabled(False)
            set_status(self._status, "left...", "info")

            def _show_right() -> None:
                set_status(self._status, "right...", "info")

            def _cleanup() -> None:
                sink.stop()
                buf.close()
                set_status(self._status, "", "info")
                self._speaker_test_btn.setEnabled(True)

            QTimer.singleShot(int((dur + gap) * 1000), _show_right)
            QTimer.singleShot(int(total_duration * 1000) + 200, _cleanup)
        except Exception as exc:
            set_status(self._status, f"speaker test failed: {exc}", "error")
            self._speaker_test_btn.setEnabled(True)

    def _on_save(self) -> None:
        from PyQt6.QtCore import QSettings
        settings = QSettings("Vox", "VoxClient")
        settings.setValue("av/camera_device", self._camera_combo.currentData())
        settings.setValue("av/input_device", self._input_combo.currentData())
        settings.setValue("av/output_device", self._output_combo.currentData())
        settings.setValue("av/noise_gate", self._mic_slider.value())
        settings.setValue("av/input_volume", self._input_vol_slider.value())
        settings.setValue("av/output_volume", self._output_vol_slider.value())
        # Push to live media client if in a voice call
        state = AppState.instance()
        state.voice_set_input_volume(_log_volume(self._input_vol_slider.value()))
        state.voice_set_output_volume(_log_volume(self._output_vol_slider.value()))
        state.voice_set_noise_gate(self._mic_slider.value() / 100.0)
        set_status(self._status, "saved", "success")

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        if self._camera is None:
            self._request_av_permission(
                "vide", self._start_camera, self._on_camera_denied,
            )
        if self._audio_source is None:
            self._request_av_permission(
                "soun", self._start_mic_capture, self._on_mic_denied,
            )

    def hideEvent(self, event) -> None:  # noqa: ANN001
        self._stop_camera()
        self._stop_mic_capture()
        super().hideEvent(event)


# -- Privacy Page ------------------------------------------------------------

class _PrivacyPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        c = AppState.instance().theme.colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(section_label("DIRECT MESSAGES"))

        self._dm_group = QButtonGroup(self)
        self._dm_radios: dict[DMPermission, QRadioButton] = {}
        radio_style = (
            f"QRadioButton {{ color: {c.text_secondary}; font-size: 12px; "
            f"border: none; spacing: 6px; padding: 2px 0; }}"
            f"QRadioButton::indicator {{ width: 14px; height: 14px; "
            f"border: 2px solid {c.text_dim}; border-radius: 9px; background: transparent; }}"
            f"QRadioButton::indicator:checked {{ background-color: {c.accent}; "
            f"border-color: {c.accent_bright}; }}"
        )
        labels = {
            DMPermission.everyone: "Everyone",
            DMPermission.friends_only: "Friends Only",
            DMPermission.mutual_servers: "Mutual Servers",
            DMPermission.nobody: "Nobody",
        }
        for perm, label in labels.items():
            rb = QRadioButton(label)
            rb.setStyleSheet(radio_style)
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            self._dm_group.addButton(rb)
            self._dm_radios[perm] = rb
            layout.addWidget(rb)

        self._dm_group.buttonClicked.connect(self._on_dm_changed)

        layout.addSpacing(8)
        layout.addWidget(separator())
        layout.addSpacing(4)

        layout.addWidget(section_label("BLOCKED USERS"))
        self._block_container = QWidget()
        self._block_container.setStyleSheet("background: transparent; border: none;")
        self._block_layout = QVBoxLayout(self._block_container)
        self._block_layout.setContentsMargins(0, 0, 0, 0)
        self._block_layout.setSpacing(2)
        self._empty_label = QLabel("No blocked users")
        self._empty_label.setStyleSheet(
            f"color: {c.text_dim}; font-size: 12px; border: none; padding: 4px 0;"
        )
        self._block_layout.addWidget(self._empty_label)
        layout.addWidget(self._block_container)

        layout.addSpacing(4)
        self._status = status_label()
        layout.addWidget(self._status)

        layout.addStretch()

        self._load_data()

    @asyncSlot()
    async def _load_data(self) -> None:
        state = AppState.instance()
        if state.client is None or state.user_id is None:
            return
        try:
            dm_resp = await state.client.users.get_dm_settings(state.user_id)
            rb = self._dm_radios.get(dm_resp.dm_permission)
            if rb:
                rb.setChecked(True)
        except Exception:
            pass

        try:
            block_resp = await state.client.users.list_blocks(state.user_id)
            self._populate_blocks(block_resp.blocked_user_ids)
        except Exception:
            pass

    def _populate_blocks(self, blocked_ids: list[int]) -> None:
        c = AppState.instance().theme.colors
        clear_layout(self._block_layout)

        if not blocked_ids:
            self._empty_label = QLabel("No blocked users")
            self._empty_label.setStyleSheet(
                f"color: {c.text_dim}; font-size: 12px; border: none; padding: 4px 0;"
            )
            self._block_layout.addWidget(self._empty_label)
            return

        for uid in blocked_ids:
            row = QWidget()
            row.setStyleSheet("background: transparent; border: none;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)
            lbl = QLabel(f"User #{uid}")
            lbl.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 12px; border: none;"
            )
            rl.addWidget(lbl, stretch=1)
            unblock_btn = QPushButton("Unblock")
            unblock_btn.setFixedHeight(24)
            unblock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            unblock_btn.setStyleSheet(
                f"QPushButton {{ color: {c.text_dim}; font-size: 11px; "
                f"border: 1px solid {c.border}; border-radius: 3px; "
                f"padding: 2px 8px; background: transparent; }}"
                f"QPushButton:hover {{ color: {c.text_secondary}; "
                f"border-color: {c.accent_dim}; background-color: {c.bg_hover}; }}"
            )
            unblock_btn.clicked.connect(lambda checked, t=uid: self._on_unblock(t))
            rl.addWidget(unblock_btn)
            self._block_layout.addWidget(row)

    @asyncSlot()
    async def _on_dm_changed(self) -> None:
        state = AppState.instance()
        if state.client is None or state.user_id is None:
            return
        selected = None
        for perm, rb in self._dm_radios.items():
            if rb.isChecked():
                selected = perm
                break
        if selected is None:
            return
        try:
            await state.client.users.update_dm_settings(state.user_id, selected)
            set_status(self._status, "saved", "success")
        except Exception as exc:
            set_status(self._status, str(exc), "error")

    @asyncSlot()
    async def _on_unblock(self, target_id: int) -> None:
        state = AppState.instance()
        if state.client is None or state.user_id is None:
            return
        try:
            await state.client.users.unblock(state.user_id, target_id)
            block_resp = await state.client.users.list_blocks(state.user_id)
            self._populate_blocks(block_resp.blocked_user_ids)
            set_status(self._status, "unblocked", "success")
        except Exception as exc:
            set_status(self._status, str(exc), "error")


# -- About Page --------------------------------------------------------------

class _AboutPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        c = AppState.instance().theme.colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(section_label("APP INFO"))

        from PyQt6.QtCore import PYQT_VERSION_STR
        import vox_client

        info_items = [
            ("Version", vox_client.__version__),
            ("Python", sys.version.split()[0]),
            ("Qt", PYQT_VERSION_STR),
        ]
        for label, value in info_items:
            layout.addWidget(field_label(label))
            val_lbl = QLabel(value)
            val_lbl.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 12px; border: none; padding: 2px 0 4px 0;"
            )
            val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(val_lbl)

        layout.addSpacing(4)
        layout.addWidget(separator())
        layout.addSpacing(4)

        layout.addWidget(section_label("THIRD-PARTY LICENSES"))

        layout.addSpacing(4)
        mdi_name = QLabel("Material Design Icons")
        mdi_name.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 13px; font-weight: 600; border: none;"
        )
        layout.addWidget(mdi_name)

        mdi_author = QLabel("Pictogrammers")
        mdi_author.setStyleSheet(
            f"color: {c.text_dim}; font-size: 11px; border: none; padding: 2px 0;"
        )
        layout.addWidget(mdi_author)

        mdi_license = QLabel("Apache License 2.0")
        mdi_license.setStyleSheet(
            f"color: {c.text_dim}; font-size: 11px; border: none; padding: 0 0 2px 0;"
        )
        layout.addWidget(mdi_license)

        mdi_note = QLabel(
            "SVG icons used for UI controls throughout the application."
        )
        mdi_note.setWordWrap(True)
        mdi_note.setStyleSheet(
            f"color: {c.text_dim}; font-size: 11px; border: none; padding: 0 0 8px 0;"
        )
        layout.addWidget(mdi_note)

        layout.addWidget(separator())
        layout.addSpacing(4)

        jb_name = QLabel("JetBrains Mono")
        jb_name.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 13px; font-weight: 600; border: none;"
        )
        layout.addWidget(jb_name)

        jb_author = QLabel("JetBrains")
        jb_author.setStyleSheet(
            f"color: {c.text_dim}; font-size: 11px; border: none; padding: 2px 0;"
        )
        layout.addWidget(jb_author)

        jb_license = QLabel("SIL Open Font License 1.1")
        jb_license.setStyleSheet(
            f"color: {c.text_dim}; font-size: 11px; border: none; padding: 0 0 2px 0;"
        )
        layout.addWidget(jb_license)

        jb_note = QLabel(
            "Monospace typeface used as the application font."
        )
        jb_note.setWordWrap(True)
        jb_note.setStyleSheet(
            f"color: {c.text_dim}; font-size: 11px; border: none; padding: 0 0 8px 0;"
        )
        layout.addWidget(jb_note)

        layout.addWidget(separator())
        layout.addSpacing(4)

        ctp_name = QLabel("Catppuccin")
        ctp_name.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 13px; font-weight: 600; border: none;"
        )
        layout.addWidget(ctp_name)

        ctp_author = QLabel("Catppuccin Org")
        ctp_author.setStyleSheet(
            f"color: {c.text_dim}; font-size: 11px; border: none; padding: 2px 0;"
        )
        layout.addWidget(ctp_author)

        ctp_license = QLabel("MIT License")
        ctp_license.setStyleSheet(
            f"color: {c.text_dim}; font-size: 11px; border: none; padding: 0 0 2px 0;"
        )
        layout.addWidget(ctp_license)

        ctp_note = QLabel(
            "Pastel color palette used for application theming."
        )
        ctp_note.setWordWrap(True)
        ctp_note.setStyleSheet(
            f"color: {c.text_dim}; font-size: 11px; border: none; padding: 0 0 8px 0;"
        )
        layout.addWidget(ctp_note)

        layout.addStretch()


# -- Main Dialog -------------------------------------------------------------

_NAV_ITEMS = [
    ("Account", "account.svg"),
    ("Audio && Video", "video.svg"),
    ("Privacy", "account-cancel.svg"),
    ("Appearance", "cog.svg"),
    ("About", "card-account-details.svg"),
]


class UserSettingsDialog(BaseSettingsDialog):
    """Frameless user settings dialog with sidebar navigation."""

    logout_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("USER SETTINGS", _NAV_ITEMS, parent)

        # Live-update when theme hue changes
        AppState.instance().theme_changed.connect(self._on_theme_changed)

    def _build_pages(self) -> None:
        # Remove existing pages
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.deleteLater()

        self._account_page = _AccountPage()
        self._account_page.logout_requested.connect(self._on_logout)
        self._av_page = _AudioVideoPage()
        self._privacy_page = _PrivacyPage()
        self._appearance_page = _AppearancePage()
        self._about_page = _AboutPage()

        for page in (self._account_page, self._av_page, self._privacy_page, self._appearance_page, self._about_page):
            self._add_page(page)

    def _on_theme_changed(self) -> None:
        self._restyle()
        current = self._active_nav
        self._build_pages()
        self._on_nav_clicked(current)

    def _on_logout(self) -> None:
        self.logout_requested.emit()
        self.accept()
