"""Member sidebar – 200px panel showing server members grouped by presence."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from vox_client.state import AppState


class _MemberItem(QWidget):
    """Single member entry with avatar and name."""

    def __init__(self, user_id: int) -> None:
        super().__init__()
        self.user_id = user_id
        self.setFixedHeight(32)

        state = AppState.instance()
        c = state.theme.colors

        from PyQt6.QtWidgets import QHBoxLayout

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 2, 8, 2)
        layout.setSpacing(8)

        # Avatar circle
        name = state.get_display_name(user_id)
        role_color = state.get_role_color(user_id) or c.accent_dim

        avatar = QLabel(name[0].upper() if name else "?")
        avatar.setFixedSize(24, 24)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background-color: {role_color}; color: {c.bg_deep}; "
            f"border-radius: 12px; font-size: 10px; font-weight: bold;"
        )
        layout.addWidget(avatar)

        # Status dot overlay (we put it on avatar via margin hack — simpler: separate dot)
        presence = state.get_presence(user_id)
        status = getattr(presence, "status", "offline") if presence else "offline"
        dot_colors = {"online": c.accent_bright, "idle": c.status_idle, "dnd": c.status_danger, "offline": c.status_offline}
        dot_color = dot_colors.get(status, c.status_offline)

        dot = QLabel("\u25cf")
        dot.setFixedWidth(8)
        dot.setStyleSheet(f"color: {dot_color}; font-size: 8px;")
        layout.addWidget(dot)

        # Name
        name_label = QLabel(name)
        name_color = state.get_role_color(user_id) or c.text_secondary
        name_label.setStyleSheet(f"color: {name_color}; font-size: 12px;")
        layout.addWidget(name_label, stretch=1)


class MemberSidebar(QFrame):
    """Right panel listing members grouped by presence status."""

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

    def refresh(self) -> None:
        """Rebuild the member list from cached data."""
        state = AppState.instance()
        c = state.theme.colors

        # Clear
        while self._list_layout.count():
            child = self._list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

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
                f"color: {c.text_dim}; font-size: 10px; font-weight: bold; "
                f"padding: 12px 0 4px 0; letter-spacing: 1px;"
            )
            self._list_layout.addWidget(header)

            for uid in sorted(user_ids, key=lambda u: state.get_display_name(u).lower()):
                self._list_layout.addWidget(_MemberItem(uid))

        _add_group("ONLINE", online)
        _add_group("IDLE", idle)
        _add_group("OFFLINE", offline)

        self._list_layout.addStretch()
