"""Mini user profile popup card for DM initiation."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qasync import asyncSlot

from vox_client.state import AppState
from vox_client.widgets.avatar import AvatarWidget
from vox_client.widgets.ui_helpers import small_accent_button

log = logging.getLogger(__name__)


class UserProfileCard(QWidget):
    """A mini popup that appears when clicking a username.

    Shows avatar, display name, handle, presence status, and a
    "Message" button that opens/creates a DM.
    """

    message_clicked = pyqtSignal(int)  # emits dm_id

    def __init__(self, user_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._user_id = user_id
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedWidth(220)

        state = AppState.instance()
        c = state.theme.colors

        self.setStyleSheet(
            f"background-color: {c.bg_panel}; border: 1px solid {c.border}; "
            f"border-radius: 6px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Top row: avatar + name column
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        top_row.addWidget(AvatarWidget(user_id, size=40, parent=self))

        name_col = QVBoxLayout()
        name_col.setSpacing(2)

        display_name = state.get_display_name(user_id)
        name_label = QLabel(display_name)
        name_label.setStyleSheet(
            f"color: {c.text_primary}; font-size: 14px; font-weight: 600; border: none;"
        )
        name_col.addWidget(name_label)

        member = state._members.get(user_id)
        username = getattr(member, "username", "") if member else ""
        if username:
            handle_label = QLabel(f"@{username}")
            handle_label.setStyleSheet(
                f"color: {c.text_dim}; font-size: 11px; border: none;"
            )
            name_col.addWidget(handle_label)

        top_row.addLayout(name_col, stretch=1)
        layout.addLayout(top_row)

        # Presence status
        presence = state.get_presence(user_id)
        status = getattr(presence, "status", "offline") if presence else "offline"
        dot_colors = {
            "online": c.status_success,
            "idle": c.status_idle,
            "dnd": c.status_danger,
            "offline": c.status_offline,
        }
        dot_color = dot_colors.get(status, c.status_offline)
        status_labels = {
            "online": "Online", "idle": "Idle",
            "dnd": "Do Not Disturb", "offline": "Offline",
        }
        status_text = status_labels.get(status, "Offline")

        status_row = QHBoxLayout()
        status_row.setSpacing(4)
        dot = QLabel("\u25cf")
        dot.setStyleSheet(f"color: {dot_color}; font-size: 10px; border: none;")
        dot.setFixedWidth(12)
        status_row.addWidget(dot)
        status_lbl = QLabel(status_text)
        status_lbl.setStyleSheet(f"color: {c.text_secondary}; font-size: 11px; border: none;")
        status_row.addWidget(status_lbl, stretch=1)
        layout.addLayout(status_row)

        # Action buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        # Don't show message button for self
        if user_id != state.user_id:
            msg_btn = small_accent_button("Message", 90, height=26)
            msg_btn.clicked.connect(self._on_message_clicked)
            btn_row.addWidget(msg_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    def show_near(self, global_pos: QPoint) -> None:
        """Position the card near the given global coordinates and show it."""
        self.adjustSize()
        # Offset slightly so the card doesn't overlap the click target
        self.move(global_pos.x() + 8, global_pos.y() - 20)
        self.show()

    @asyncSlot()
    async def _on_message_clicked(self) -> None:
        state = AppState.instance()
        if state.client is None:
            self.close()
            return
        try:
            dm = await state.client.dms.open(recipient_id=self._user_id)
            state._dms[dm.dm_id] = dm
            state.dm_list_changed.emit()
            self.message_clicked.emit(dm.dm_id)
            self.close()
        except Exception:
            log.error("Failed to open DM with user %d", self._user_id, exc_info=True)
            self.close()

    def keyPressEvent(self, event) -> None:  # noqa: ANN001
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
