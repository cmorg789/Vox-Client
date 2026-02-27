"""Member sidebar – 200px panel showing server members grouped by presence."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QVBoxLayout, QWidget

from vox_client.state import AppState
from vox_client.widgets.avatar import AvatarWidget
from vox_client.widgets.ui_helpers import clear_layout


class _MemberItem(QWidget):
    """Single member entry with avatar, presence dot, name, and status text."""

    send_message_requested = Signal(int)  # user_id

    def __init__(self, user_id: int) -> None:
        super().__init__()
        self.user_id = user_id
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        state = AppState.instance()
        c = state.theme.colors

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 8, 4)
        layout.setSpacing(8)

        # Avatar circle
        name = state.get_display_name(user_id)
        layout.addWidget(AvatarWidget(user_id, size=24, parent=self))

        # Status dot
        presence = state.get_presence(user_id)
        status = getattr(presence, "status", "offline") if presence else "offline"
        dot_colors = {
            "online": c.status_success,
            "idle": c.status_idle,
            "dnd": c.status_danger,
            "offline": c.status_offline,
        }
        dot_color = dot_colors.get(status, c.status_offline)

        dot = QLabel("\u25cf")
        dot.setFixedWidth(8)
        dot.setStyleSheet(f"color: {dot_color}; font-size: 8px;")
        layout.addWidget(dot)

        # Name + status text column
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)

        name_label = QLabel(name)
        name_color = state.get_role_color(user_id) or c.text_secondary
        name_label.setStyleSheet(f"color: {name_color}; font-size: 13px;")
        text_col.addWidget(name_label)

        # Status text (custom status or default label)
        custom = getattr(presence, "custom_status", None) if presence else None
        status_labels = {"online": "Online", "idle": "Idle", "dnd": "Do Not Disturb", "offline": "Offline"}
        status_text = custom if custom else status_labels.get(status, "Offline")
        status_lbl = QLabel(status_text)
        status_lbl.setStyleSheet(f"color: {c.text_dim}; font-size: 10px;")
        text_col.addWidget(status_lbl)

        layout.addLayout(text_col, stretch=1)

    def contextMenuEvent(self, event) -> None:  # noqa: ANN001
        state = AppState.instance()
        c = state.theme.colors
        # Don't show context menu for our own entry
        if self.user_id == state.user_id:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background-color: {c.bg_panel}; color: {c.text_primary}; "
            f"border: 1px solid {c.border_bright}; border-radius: 4px; padding: 4px; "
            f"font-size: 12px; }}"
            f"QMenu::item {{ padding: 6px 12px; border-radius: 3px; }}"
            f"QMenu::item:selected {{ background-color: {c.bg_active}; }}"
        )
        send_msg = menu.addAction("Send Message")
        action = menu.exec(event.globalPos())
        if action is send_msg:
            self.send_message_requested.emit(self.user_id)

    profile_dm_opened = Signal(int)  # dm_id from profile card

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            from vox_client.widgets.user_profile_card import UserProfileCard
            card = UserProfileCard(self.user_id, parent=None)
            card.message_clicked.connect(self.profile_dm_opened.emit)
            card.show_near(event.globalPosition().toPoint())


class MemberSidebar(QFrame):
    """Right panel listing members grouped by presence status."""

    send_message_requested = Signal(int)  # user_id (from context menu)
    open_dm_requested = Signal(int)       # dm_id (from profile card)

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(200)

        state = AppState.instance()
        c = state.theme.colors
        self.setStyleSheet(f"background-color: {c.bg_panel}; border-left: 1px solid {c.border};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none;")

        self._container = QWidget()
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(0, 8, 0, 8)
        self._list_layout.setSpacing(0)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._container)
        outer.addWidget(scroll)

        # Connect signals for live updates
        state.presence_updated.connect(lambda _: self.refresh())
        state.member_joined.connect(lambda _: self.refresh())
        state.member_left.connect(lambda _: self.refresh())
        state.member_updated.connect(lambda _: self.refresh())

    def restyle(self) -> None:
        """Re-apply container-level inline styles after a theme change."""
        c = AppState.instance().theme.colors
        self.setStyleSheet(f"background-color: {c.bg_panel}; border-left: 1px solid {c.border};")

    def refresh(self) -> None:
        """Rebuild the member list from cached data."""
        log.debug("Refreshing member sidebar (%d members cached)", len(AppState.instance()._members))
        state = AppState.instance()
        c = state.theme.colors

        # Clear
        clear_layout(self._list_layout)

        # Group members by status
        online: list[int] = []
        idle: list[int] = []
        offline: list[int] = []

        for uid in state._members:
            presence = state.get_presence(uid)
            status = getattr(presence, "status", "offline") if presence else "offline"
            if status in ("online", "dnd"):
                online.append(uid)
            elif status == "idle":
                idle.append(uid)
            else:
                offline.append(uid)

        def _add_group(label: str, user_ids: list[int]) -> None:
            if not user_ids:
                return
            header = QLabel(f"  {label} \u2014 {len(user_ids)}")
            header.setStyleSheet(
                f"color: {c.text_dim}; font-size: 10px; font-weight: 600; "
                f"padding: 12px 0 4px 0; letter-spacing: 1px;"
            )
            self._list_layout.addWidget(header)

            for uid in sorted(user_ids, key=lambda u: state.get_display_name(u).lower()):
                item = _MemberItem(uid)
                item.send_message_requested.connect(self.send_message_requested.emit)
                item.profile_dm_opened.connect(self.open_dm_requested.emit)
                self._list_layout.addWidget(item)

        _add_group("ONLINE", online)
        _add_group("IDLE", idle)
        _add_group("OFFLINE", offline)

        self._list_layout.addStretch()
