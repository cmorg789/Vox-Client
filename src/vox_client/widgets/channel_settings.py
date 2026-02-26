"""Channel settings dialog – overview (name/topic) and permission overrides."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from vox_sdk.errors import VoxHTTPError
from vox_sdk.permissions import (
    ADD_REACTIONS,
    ATTACH_FILES,
    CONNECT,
    DEAFEN_MEMBERS,
    MENTION_EVERYONE,
    MOVE_MEMBERS,
    MUTE_MEMBERS,
    PRIORITY_SPEAKER,
    READ_HISTORY,
    SEND_EMBEDS,
    SEND_MESSAGES,
    SPEAK,
    STREAM,
    VIDEO,
    VIEW_SPACE,
)

from vox_client._frozen import ICONS_DIR as _ICONS_DIR
from vox_client.state import AppState
from vox_client.theme import role_color_for_int
from vox_client.widgets.base_settings_dialog import BaseSettingsDialog
from vox_client.widgets.icons import tinted_icon
from vox_client.widgets.ui_helpers import (
    action_button,
    clear_layout,
    section_label,
    set_status,
    status_label,
)


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, VoxHTTPError) and exc.error:
        return exc.error
    return str(exc)


# -- Permission definitions ---------------------------------------------------

_FEED_PERMS: list[tuple[str, int]] = [
    ("View Space", VIEW_SPACE),
    ("Send Messages", SEND_MESSAGES),
    ("Send Embeds", SEND_EMBEDS),
    ("Attach Files", ATTACH_FILES),
    ("Add Reactions", ADD_REACTIONS),
    ("Read History", READ_HISTORY),
    ("Mention Everyone", MENTION_EVERYONE),
]

_ROOM_PERMS: list[tuple[str, int]] = [
    ("View Space", VIEW_SPACE),
    ("Connect", CONNECT),
    ("Speak", SPEAK),
    ("Video", VIDEO),
    ("Stream", STREAM),
    ("Priority Speaker", PRIORITY_SPEAKER),
    ("Mute Members", MUTE_MEMBERS),
    ("Deafen Members", DEAFEN_MEMBERS),
    ("Move Members", MOVE_MEMBERS),
]


# -- Overview page ------------------------------------------------------------


class _OverviewPage(QWidget):
    """Name and topic editing for a feed or room."""

    def __init__(self, item_type: str, item_id: int) -> None:
        super().__init__()
        self._item_type = item_type
        self._item_id = item_id
        state = AppState.instance()
        c = state.theme.colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Name
        layout.addWidget(section_label("CHANNEL NAME", top_pad=12))
        if item_type == "feed":
            feed = state._feeds.get(item_id)
            current_name = feed.name if feed else ""
            current_topic = feed.topic if feed else ""
        else:
            room = state._rooms.get(item_id)
            current_name = room.name if room else ""
            current_topic = ""

        self._name_input = QLineEdit(current_name)
        self._name_input.setStyleSheet(
            f"background-color: {c.bg_input}; color: {c.text_primary}; "
            f"border: 1px solid {c.border}; border-radius: 4px; "
            f"padding: 4px 8px; font-size: 12px;"
        )
        layout.addWidget(self._name_input)

        # Topic (feeds only)
        if item_type == "feed":
            layout.addWidget(section_label("TOPIC", top_pad=12))
            self._topic_input = QTextEdit()
            self._topic_input.setFixedHeight(80)
            self._topic_input.setPlaceholderText("Set a topic for this channel...")
            self._topic_input.setPlainText(current_topic or "")
            self._topic_input.setStyleSheet(
                f"background-color: {c.bg_input}; color: {c.text_primary}; "
                f"border: 1px solid {c.border}; border-radius: 4px; "
                f"padding: 4px 8px; font-size: 12px;"
            )
            layout.addWidget(self._topic_input)
        else:
            self._topic_input = None

        layout.addSpacing(12)
        self._status = status_label()
        layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        self._save_btn = action_button("[ SAVE ]")
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)
        layout.addLayout(btn_row)

        layout.addStretch()

    @asyncSlot()
    async def _on_save(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        self._save_btn.setEnabled(False)
        set_status(self._status, "saving...", "info")
        try:
            name = self._name_input.text().strip()
            if not name:
                set_status(self._status, "Name cannot be empty.", "error")
                self._save_btn.setEnabled(True)
                return

            if self._item_type == "feed":
                topic = self._topic_input.toPlainText().strip() if self._topic_input else None
                resp = await state.client.channels.update_feed(
                    self._item_id, name=name, topic=topic,
                )
                state._feeds[self._item_id] = resp
                # Update layout cache
                if state._layout is not None:
                    for f in state._layout.feeds:
                        if f.feed_id == self._item_id:
                            f.name = resp.name
                            break
            else:
                resp = await state.client.channels.update_room(
                    self._item_id, name=name,
                )
                state._rooms[self._item_id] = resp
                if state._layout is not None:
                    for r in state._layout.rooms:
                        if r.room_id == self._item_id:
                            r.name = resp.name
                            break

            state.layout_changed.emit()
            set_status(self._status, "Saved.", "success")
        except Exception as exc:
            log.error("Failed to update %s %d", self._item_type, self._item_id, exc_info=True)
            set_status(self._status, _friendly_error(exc), "error")
        finally:
            self._save_btn.setEnabled(True)


# -- Permissions page ---------------------------------------------------------


class _RoleButton(QPushButton):
    """Selectable role button in the left list."""

    def __init__(self, role_id: int, name: str, color: int | None) -> None:
        super().__init__(name)
        self.role_id = role_id
        c = AppState.instance().theme.colors
        text_color = role_color_for_int(color) if color else c.text_secondary
        self.setFixedHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QPushButton {{ text-align: left; padding: 0 10px; font-size: 12px; "
            f"color: {text_color}; border: none; border-radius: 3px; "
            f"background: transparent; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )

    def set_active(self, active: bool) -> None:
        c = AppState.instance().theme.colors
        if active:
            self.setStyleSheet(
                f"QPushButton {{ text-align: left; padding: 0 10px; font-size: 12px; "
                f"color: {c.text_primary}; border: none; border-radius: 3px; "
                f"background-color: {c.bg_active}; font-weight: 600; }}"
            )
        else:
            state = AppState.instance()
            role = state._roles.get(self.role_id)
            text_color = role_color_for_int(role.color) if role and role.color else c.text_secondary
            self.setStyleSheet(
                f"QPushButton {{ text-align: left; padding: 0 10px; font-size: 12px; "
                f"color: {text_color}; border: none; border-radius: 3px; "
                f"background: transparent; }}"
                f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
            )


class _PermissionsPage(QWidget):
    """Per-role permission override editor for a channel."""

    def __init__(self, item_type: str, item_id: int) -> None:
        super().__init__()
        self._item_type = item_type
        self._item_id = item_id
        self._selected_role_id: int | None = None
        self._role_buttons: list[_RoleButton] = []
        # Map perm label -> (allow_cb, deny_cb, bit)
        self._perm_widgets: dict[str, tuple[QCheckBox, QCheckBox, int]] = {}
        # Cached overrides: role_id -> (allow, deny)
        self._overrides: dict[int, tuple[int, int]] = {}

        state = AppState.instance()
        c = state.theme.colors

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -- Left: role list --------------------------------------------------
        left_panel = QWidget()
        left_panel.setFixedWidth(160)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(2)

        left_layout.addWidget(section_label("ROLES", top_pad=4))

        role_scroll = QScrollArea()
        role_scroll.setWidgetResizable(True)
        role_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        role_scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: transparent; }}"
            f"QScrollBar:vertical {{ width: 6px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {c.accent_dim}; "
            f"border-radius: 3px; min-height: 20px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )
        role_container = QWidget()
        role_container.setStyleSheet("background: transparent; border: none;")
        self._role_list_layout = QVBoxLayout(role_container)
        self._role_list_layout.setContentsMargins(0, 0, 0, 0)
        self._role_list_layout.setSpacing(1)

        # Populate roles
        sorted_roles = sorted(state._roles.values(), key=lambda r: r.position)
        for role in sorted_roles:
            btn = _RoleButton(role.role_id, role.name, role.color)
            btn.clicked.connect(lambda checked, rid=role.role_id: self._on_role_selected(rid))
            self._role_list_layout.addWidget(btn)
            self._role_buttons.append(btn)

        self._role_list_layout.addStretch()
        role_scroll.setWidget(role_container)
        left_layout.addWidget(role_scroll, stretch=1)

        outer.addWidget(left_panel)

        # Vertical separator
        sep = QWidget()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background-color: {c.border};")
        outer.addWidget(sep)

        # -- Right: permission overrides --------------------------------------
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 0, 0, 0)
        right_layout.setSpacing(4)

        right_layout.addWidget(section_label("PERMISSION OVERRIDES", top_pad=4))

        # Empty state
        self._empty_label = QLabel("Select a role to edit overrides.")
        self._empty_label.setStyleSheet(
            f"color: {c.text_dim}; font-size: 12px; border: none; padding: 20px 0;"
        )
        right_layout.addWidget(self._empty_label)

        # Override form (hidden initially)
        self._form = QWidget()
        self._form.setVisible(False)
        form_layout = QVBoxLayout(self._form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(2)

        perms_list = _FEED_PERMS if item_type == "feed" else _ROOM_PERMS
        for label, bit in perms_list:
            row = QHBoxLayout()
            row.setSpacing(8)

            perm_label = QLabel(label)
            perm_label.setFixedWidth(130)
            perm_label.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 11px; border: none;"
            )
            row.addWidget(perm_label)

            allow_cb = QCheckBox("Allow")
            allow_cb.setStyleSheet(
                f"QCheckBox {{ color: {c.status_success}; font-size: 11px; "
                f"border: none; spacing: 4px; }}"
                f"QCheckBox::indicator {{ width: 16px; height: 16px; "
                f"border: 1px solid {c.border_bright}; border-radius: 3px; "
                f"background: {c.bg_input}; }}"
                f"QCheckBox::indicator:checked {{ background: {c.accent_dim}; "
                f"border-color: {c.status_success}; }}"
            )
            row.addWidget(allow_cb)

            deny_cb = QCheckBox("Deny")
            deny_cb.setStyleSheet(
                f"QCheckBox {{ color: {c.status_danger}; font-size: 11px; "
                f"border: none; spacing: 4px; }}"
                f"QCheckBox::indicator {{ width: 16px; height: 16px; "
                f"border: 1px solid {c.border_bright}; border-radius: 3px; "
                f"background: {c.bg_input}; }}"
                f"QCheckBox::indicator:checked {{ background: {c.status_danger}; "
                f"border-color: {c.status_danger}; }}"
            )
            row.addWidget(deny_cb)

            # Mutual exclusion: checking allow unchecks deny and vice versa
            allow_cb.toggled.connect(lambda checked, d=deny_cb: d.setChecked(False) if checked else None)
            deny_cb.toggled.connect(lambda checked, a=allow_cb: a.setChecked(False) if checked else None)

            row.addStretch()
            form_layout.addLayout(row)
            self._perm_widgets[label] = (allow_cb, deny_cb, bit)

        form_layout.addSpacing(8)
        self._perm_status = status_label()
        form_layout.addWidget(self._perm_status)

        perm_btn_row = QHBoxLayout()
        perm_btn_row.setSpacing(8)
        perm_btn_row.addStretch()
        self._perm_save_btn = action_button("[ SAVE ]")
        self._perm_save_btn.clicked.connect(self._on_save_overrides)
        perm_btn_row.addWidget(self._perm_save_btn)
        form_layout.addLayout(perm_btn_row)

        form_layout.addStretch()
        right_layout.addWidget(self._form, stretch=1)

        outer.addWidget(right_panel, stretch=1)

        # Kick off loading overrides
        self._load_overrides()

    @asyncSlot()
    async def _load_overrides(self) -> None:
        """Fetch current channel data to populate override cache."""
        state = AppState.instance()
        if state.client is None:
            return
        try:
            if self._item_type == "feed":
                resp = await state.client.channels.get_feed(self._item_id)
            else:
                resp = await state.client.channels.get_room(self._item_id)
            self._overrides.clear()
            for ov in resp.permission_overrides:
                if ov.target_type == "role":
                    self._overrides[ov.target_id] = (ov.allow, ov.deny)
            # Refresh UI if a role is selected
            if self._selected_role_id is not None:
                self._populate_checkboxes(self._selected_role_id)
        except Exception:
            log.error("Failed to load overrides for %s %d", self._item_type, self._item_id, exc_info=True)

    def _on_role_selected(self, role_id: int) -> None:
        self._selected_role_id = role_id
        for btn in self._role_buttons:
            btn.set_active(btn.role_id == role_id)
        self._empty_label.setVisible(False)
        self._form.setVisible(True)
        self._populate_checkboxes(role_id)
        set_status(self._perm_status, "", "info")

    def _populate_checkboxes(self, role_id: int) -> None:
        allow, deny = self._overrides.get(role_id, (0, 0))
        for _label, (allow_cb, deny_cb, bit) in self._perm_widgets.items():
            # Block signals to avoid mutual-exclusion side effects during population
            allow_cb.blockSignals(True)
            deny_cb.blockSignals(True)
            allow_cb.setChecked(bool(allow & bit))
            deny_cb.setChecked(bool(deny & bit))
            allow_cb.blockSignals(False)
            deny_cb.blockSignals(False)

    @asyncSlot()
    async def _on_save_overrides(self) -> None:
        if self._selected_role_id is None:
            return
        state = AppState.instance()
        if state.client is None:
            return

        self._perm_save_btn.setEnabled(False)
        set_status(self._perm_status, "saving...", "info")

        # Compute allow/deny bitmasks from checkboxes
        allow = 0
        deny = 0
        for _label, (allow_cb, deny_cb, bit) in self._perm_widgets.items():
            if allow_cb.isChecked():
                allow |= bit
            if deny_cb.isChecked():
                deny |= bit

        try:
            role_id = self._selected_role_id
            if allow == 0 and deny == 0:
                # All inherit — delete the override
                if self._item_type == "feed":
                    await state.client.roles.delete_feed_override(
                        self._item_id, "role", role_id,
                    )
                else:
                    await state.client.roles.delete_room_override(
                        self._item_id, "role", role_id,
                    )
                self._overrides.pop(role_id, None)
            else:
                if self._item_type == "feed":
                    await state.client.roles.set_feed_override(
                        self._item_id, "role", role_id, allow, deny,
                    )
                else:
                    await state.client.roles.set_room_override(
                        self._item_id, "role", role_id, allow, deny,
                    )
                self._overrides[role_id] = (allow, deny)
            set_status(self._perm_status, "Saved.", "success")
        except Exception as exc:
            log.error(
                "Failed to save overrides for %s %d role %d",
                self._item_type, self._item_id, self._selected_role_id,
                exc_info=True,
            )
            set_status(self._perm_status, _friendly_error(exc), "error")
        finally:
            self._perm_save_btn.setEnabled(True)


# -- Dialog -------------------------------------------------------------------


class ChannelSettingsDialog(BaseSettingsDialog):
    """Settings dialog for a feed or room channel."""

    def __init__(
        self,
        item_type: str,
        item_id: int,
        parent: QWidget | None = None,
    ) -> None:
        self._item_type = item_type
        self._item_id = item_id
        label = "FEED SETTINGS" if item_type == "feed" else "ROOM SETTINGS"
        super().__init__(
            title=label,
            nav_items=[
                ("Overview", "text-box-outline.svg"),
                ("Permissions", "shield-lock.svg"),
            ],
            parent=parent,
        )

    def _build_pages(self) -> None:
        self._add_page(_OverviewPage(self._item_type, self._item_id))
        self._add_page(_PermissionsPage(self._item_type, self._item_id))
