"""Server settings dialog – frameless modal with sidebar navigation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from vox_sdk.errors import VoxHTTPError
from vox_sdk.permissions import (
    ADD_REACTIONS,
    ADMINISTRATOR,
    ATTACH_FILES,
    BAN_MEMBERS,
    CHANGE_NICKNAME,
    CONNECT,
    CREATE_INVITES,
    CREATE_THREADS,
    DEAFEN_MEMBERS,
    KICK_MEMBERS,
    MANAGE_2FA,
    MANAGE_EMOJI,
    MANAGE_MESSAGES,
    MANAGE_NICKNAMES,
    MANAGE_REPORTS,
    MANAGE_ROLES,
    MANAGE_SERVER,
    MANAGE_SPACES,
    MANAGE_THREADS,
    MANAGE_WEBHOOKS,
    MENTION_EVERYONE,
    MOVE_MEMBERS,
    MUTE_MEMBERS,
    PRIORITY_SPEAKER,
    READ_HISTORY,
    SEND_EMBEDS,
    SEND_IN_THREADS,
    SEND_MESSAGES,
    SPEAK,
    STAGE_MODERATOR,
    STREAM,
    VIDEO,
    VIEW_AUDIT_LOG,
    VIEW_REPORTS,
    VIEW_SPACE,
)

from vox_client._frozen import ICONS_DIR as _ICONS_DIR
from vox_client.state import AppState
from vox_client.theme import role_color_for_int
from vox_client.widgets.avatar import AvatarWidget
from vox_client.widgets.base_settings_dialog import BaseSettingsDialog
from vox_client.widgets.icons import tinted_icon
from vox_client.widgets.toast import show_toast
from vox_client.widgets.ui_helpers import (
    action_button,
    danger_button,
    section_label,
    separator,
    set_status,
    status_label,
)


def _friendly_error(exc: Exception) -> str:
    """Extract a user-friendly message from a VoxHTTPError, or fall back to str()."""
    if isinstance(exc, VoxHTTPError) and exc.error:
        return exc.error.message
    return str(exc)


def _make_scroll_area() -> tuple[QScrollArea, QWidget, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setStyleSheet("border: none; background: transparent;")
    container = QWidget()
    container.setStyleSheet("background: transparent;")
    lay = QVBoxLayout(container)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    lay.setAlignment(Qt.AlignmentFlag.AlignTop)
    scroll.setWidget(container)
    return scroll, container, lay


# -- Invites Page ------------------------------------------------------------


class _InviteRow(QWidget):
    """Single invite row in the scrollable list."""

    deleted = Signal(str)  # code

    def __init__(self, invite) -> None:  # noqa: ANN001
        super().__init__()
        self._code = invite.code
        self.setFixedHeight(36)

        state = AppState.instance()
        c = state.theme.colors

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 2, 8, 2)
        row.setSpacing(10)

        # Invite code (monospace, clickable)
        self._code_btn = QPushButton(invite.code)
        self._code_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._code_btn.setStyleSheet(
            f"QPushButton {{ color: {c.accent}; font-size: 12px; font-family: monospace; "
            f"border: none; background: transparent; text-align: left; }}"
            f"QPushButton:hover {{ text-decoration: underline; }}"
        )
        self._code_btn.clicked.connect(self._copy_code)
        row.addWidget(self._code_btn)

        # Creator name
        creator = state.get_display_name(invite.creator_id)
        creator_lbl = QLabel(creator)
        creator_lbl.setStyleSheet(
            f"color: {c.text_dim}; font-size: 11px; border: none;"
        )
        row.addWidget(creator_lbl)

        row.addStretch()

        # Uses count
        max_uses = invite.max_uses if invite.max_uses else "\u221e"
        uses_lbl = QLabel(f"{invite.uses}/{max_uses} uses")
        uses_lbl.setStyleSheet(f"color: {c.text_dim}; font-size: 11px; border: none;")
        row.addWidget(uses_lbl)

        # Expiry
        if invite.expires_at:
            now = datetime.now(timezone.utc).timestamp()
            diff = invite.expires_at - now
            if diff <= 0:
                expiry_text = "expired"
            elif diff < 3600:
                expiry_text = f"{int(diff / 60)}m left"
            elif diff < 86400:
                expiry_text = f"{int(diff / 3600)}h left"
            else:
                expiry_text = f"{int(diff / 86400)}d left"
        else:
            expiry_text = "never"
        expiry_lbl = QLabel(expiry_text)
        expiry_lbl.setStyleSheet(f"color: {c.text_dim}; font-size: 11px; border: none;")
        expiry_lbl.setFixedWidth(60)
        row.addWidget(expiry_lbl)

        # Status label
        self._status = status_label()
        self._status.setFixedWidth(50)
        row.addWidget(self._status)

        # Delete button
        self._del_btn = QPushButton("\u2715")
        self._del_btn.setFixedSize(22, 22)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setStyleSheet(
            f"QPushButton {{ color: {c.status_danger}; font-size: 12px; "
            f"border: 1px solid {c.status_danger}; border-radius: 3px; "
            f"background: transparent; }}"
            f"QPushButton:hover {{ background-color: {c.status_danger}; color: {c.text_on_accent}; }}"
        )
        self._del_btn.clicked.connect(self._on_delete)
        row.addWidget(self._del_btn)

    def enterEvent(self, event) -> None:  # noqa: ANN001
        c = AppState.instance().theme.colors
        self.setStyleSheet(f"background-color: {c.bg_hover}; border-radius: 4px;")

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        self.setStyleSheet("background: transparent;")

    def _copy_code(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._code)
        set_status(self._status, "copied", "success")

    @asyncSlot()
    async def _on_delete(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        self._del_btn.setEnabled(False)
        try:
            await state.client.invites.delete(self._code)
            self.deleted.emit(self._code)
        except Exception as exc:
            log.error("Failed to delete invite %s: %s", self._code, exc)
            set_status(self._status, str(exc)[:20], "error")
        finally:
            self._del_btn.setEnabled(True)


class _InvitesPage(QWidget):
    def __init__(self) -> None:
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Top bar: section label + status + create button
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addWidget(section_label("INVITES", top_pad=12))
        top_row.addStretch()
        self._status = status_label()
        self._status.setFixedWidth(80)
        top_row.addWidget(self._status)
        self._create_btn = action_button("[ + CREATE ]", width=110)
        self._create_btn.clicked.connect(self._on_create)
        top_row.addWidget(self._create_btn)
        layout.addLayout(top_row)

        layout.addSpacing(4)

        # Scroll area for invite rows
        self._scroll, self._container, self._list_layout = _make_scroll_area()
        layout.addWidget(self._scroll, stretch=1)

        self._rows: list[_InviteRow] = []
        self._load_invites()

    @asyncSlot()
    async def _load_invites(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        try:
            resp = await state.client.invites.list()
            for invite in resp.items:
                self._add_row(invite)
        except Exception as exc:
            log.warning("Failed to load invites: %s", exc)
            set_status(self._status, str(exc)[:30], "error")

    def _add_row(self, invite, prepend: bool = False) -> None:  # noqa: ANN001
        row = _InviteRow(invite)
        row.deleted.connect(self._on_row_deleted)
        if prepend:
            self._list_layout.insertWidget(0, row)
            self._rows.insert(0, row)
        else:
            self._list_layout.addWidget(row)
            self._rows.append(row)

    def _on_row_deleted(self, code: str) -> None:
        for row in self._rows:
            if row._code == code:
                row.deleteLater()
                self._rows.remove(row)
                break

    @asyncSlot()
    async def _on_create(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        self._create_btn.setEnabled(False)
        set_status(self._status, "creating...", "info")
        try:
            invite = await state.client.invites.create()
            self._add_row(invite, prepend=True)
            set_status(self._status, "", "info")
        except Exception as exc:
            log.error("Failed to create invite: %s", exc)
            set_status(self._status, str(exc)[:30], "error")
        finally:
            self._create_btn.setEnabled(True)


# -- Emoji & Stickers Page ---------------------------------------------------


class _AssetRow(QWidget):
    """Single emoji or sticker row."""

    deleted = Signal(int)  # asset id

    def __init__(
        self, asset_id: int, name: str, creator_id: int, asset_type: str
    ) -> None:
        super().__init__()
        self.asset_id = asset_id
        self._asset_type = asset_type
        self.setFixedHeight(40)

        state = AppState.instance()
        c = state.theme.colors

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(10)

        # Name (editable)
        self._name_input = QLineEdit(name)
        self._name_input.setFixedWidth(160)
        self._name_input.setStyleSheet(
            f"background-color: {c.bg_input}; color: {c.text_primary}; "
            f"border: 1px solid {c.border}; border-radius: 3px; "
            f"padding: 2px 8px; font-size: 12px;"
        )
        self._name_input.editingFinished.connect(self._on_rename)
        row.addWidget(self._name_input)

        # Creator name
        creator = state.get_display_name(creator_id)
        creator_lbl = QLabel(creator)
        creator_lbl.setStyleSheet(
            f"color: {c.text_dim}; font-size: 11px; border: none;"
        )
        row.addWidget(creator_lbl, stretch=1)

        # Status label
        self._status = status_label()
        self._status.setFixedWidth(50)
        row.addWidget(self._status)

        # Delete button
        self._del_btn = QPushButton("\u2715")
        self._del_btn.setFixedSize(22, 22)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setStyleSheet(
            f"QPushButton {{ color: {c.status_danger}; font-size: 12px; "
            f"border: 1px solid {c.status_danger}; border-radius: 3px; "
            f"background: transparent; }}"
            f"QPushButton:hover {{ background-color: {c.status_danger}; color: {c.text_on_accent}; }}"
        )
        self._del_btn.clicked.connect(self._on_delete)
        row.addWidget(self._del_btn)

    def enterEvent(self, event) -> None:  # noqa: ANN001
        c = AppState.instance().theme.colors
        self.setStyleSheet(f"background-color: {c.bg_hover}; border-radius: 4px;")

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        self.setStyleSheet("background: transparent;")

    @asyncSlot()
    async def _on_rename(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        new_name = self._name_input.text().strip()
        if not new_name:
            return
        try:
            if self._asset_type == "emoji":
                await state.client.emoji.update_emoji(self.asset_id, new_name)
            else:
                await state.client.emoji.update_sticker(self.asset_id, new_name)
            set_status(self._status, "saved", "success")
        except Exception as exc:
            log.error(
                "Failed to rename %s %d: %s", self._asset_type, self.asset_id, exc
            )
            set_status(self._status, str(exc)[:20], "error")

    @asyncSlot()
    async def _on_delete(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        self._del_btn.setEnabled(False)
        try:
            if self._asset_type == "emoji":
                await state.client.emoji.delete_emoji(self.asset_id)
            else:
                await state.client.emoji.delete_sticker(self.asset_id)
            self.deleted.emit(self.asset_id)
        except Exception as exc:
            log.error(
                "Failed to delete %s %d: %s", self._asset_type, self.asset_id, exc
            )
            set_status(self._status, str(exc)[:20], "error")
        finally:
            self._del_btn.setEnabled(True)


class _EmojiStickersPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        c = AppState.instance().theme.colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(section_label("EMOJI && STICKERS", top_pad=12))

        # Tab row
        tab_row = QHBoxLayout()
        tab_row.setSpacing(4)
        self._emoji_tab = QPushButton("Emoji")
        self._sticker_tab = QPushButton("Stickers")
        for btn in (self._emoji_tab, self._sticker_tab):
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._emoji_tab.clicked.connect(lambda: self._switch_tab(0))
        self._sticker_tab.clicked.connect(lambda: self._switch_tab(1))
        tab_row.addWidget(self._emoji_tab)
        tab_row.addWidget(self._sticker_tab)
        tab_row.addStretch()
        layout.addLayout(tab_row)

        layout.addSpacing(4)

        # Stacked widget for emoji / sticker panels
        self._stack = QStackedWidget()

        # Emoji panel
        self._emoji_panel = QWidget()
        ep_layout = QVBoxLayout(self._emoji_panel)
        ep_layout.setContentsMargins(0, 0, 0, 0)
        ep_layout.setSpacing(4)
        ep_top = QHBoxLayout()
        self._emoji_status = status_label()
        self._emoji_status.setFixedWidth(80)
        ep_top.addWidget(self._emoji_status)
        ep_top.addStretch()
        self._emoji_upload_btn = action_button("[ + UPLOAD ]", width=110)
        self._emoji_upload_btn.clicked.connect(self._on_upload_emoji)
        ep_top.addWidget(self._emoji_upload_btn)
        ep_layout.addLayout(ep_top)
        self._emoji_scroll, self._emoji_container, self._emoji_layout = (
            _make_scroll_area()
        )
        ep_layout.addWidget(self._emoji_scroll, stretch=1)
        self._stack.addWidget(self._emoji_panel)

        # Sticker panel
        self._sticker_panel = QWidget()
        sp_layout = QVBoxLayout(self._sticker_panel)
        sp_layout.setContentsMargins(0, 0, 0, 0)
        sp_layout.setSpacing(4)
        sp_top = QHBoxLayout()
        self._sticker_status = status_label()
        self._sticker_status.setFixedWidth(80)
        sp_top.addWidget(self._sticker_status)
        sp_top.addStretch()
        self._sticker_upload_btn = action_button("[ + UPLOAD ]", width=110)
        self._sticker_upload_btn.clicked.connect(self._on_upload_sticker)
        sp_top.addWidget(self._sticker_upload_btn)
        sp_layout.addLayout(sp_top)
        self._sticker_scroll, self._sticker_container, self._sticker_layout = (
            _make_scroll_area()
        )
        sp_layout.addWidget(self._sticker_scroll, stretch=1)
        self._stack.addWidget(self._sticker_panel)

        layout.addWidget(self._stack, stretch=1)

        self._emoji_rows: list[_AssetRow] = []
        self._sticker_rows: list[_AssetRow] = []

        self._switch_tab(0)
        self._load_assets()

    def _switch_tab(self, index: int) -> None:
        c = AppState.instance().theme.colors
        self._stack.setCurrentIndex(index)
        active_style = (
            f"QPushButton {{ color: {c.text_primary}; font-size: 12px; font-weight: 600; "
            f"border: none; border-bottom: 2px solid {c.accent}; "
            f"border-radius: 0; background: transparent; padding: 4px 12px; }}"
        )
        inactive_style = (
            f"QPushButton {{ color: {c.text_dim}; font-size: 12px; "
            f"border: none; border-radius: 0; background: transparent; padding: 4px 12px; }}"
            f"QPushButton:hover {{ color: {c.text_secondary}; }}"
        )
        self._emoji_tab.setStyleSheet(active_style if index == 0 else inactive_style)
        self._sticker_tab.setStyleSheet(active_style if index == 1 else inactive_style)

    @asyncSlot()
    async def _load_assets(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        try:
            emoji_resp = await state.client.emoji.list_emoji()
            for e in emoji_resp.items:
                self._add_emoji_row(e)
        except Exception as exc:
            log.warning("Failed to load emoji: %s", exc)
            set_status(self._emoji_status, str(exc)[:30], "error")
        try:
            sticker_resp = await state.client.emoji.list_stickers()
            for s in sticker_resp.items:
                self._add_sticker_row(s)
        except Exception as exc:
            log.warning("Failed to load stickers: %s", exc)
            set_status(self._sticker_status, str(exc)[:30], "error")

    def _add_emoji_row(self, emoji, prepend: bool = False) -> None:  # noqa: ANN001
        row = _AssetRow(emoji.emoji_id, emoji.name, emoji.creator_id, "emoji")
        row.deleted.connect(self._on_emoji_deleted)
        if prepend:
            self._emoji_layout.insertWidget(0, row)
            self._emoji_rows.insert(0, row)
        else:
            self._emoji_layout.addWidget(row)
            self._emoji_rows.append(row)

    def _add_sticker_row(self, sticker, prepend: bool = False) -> None:  # noqa: ANN001
        row = _AssetRow(sticker.sticker_id, sticker.name, sticker.creator_id, "sticker")
        row.deleted.connect(self._on_sticker_deleted)
        if prepend:
            self._sticker_layout.insertWidget(0, row)
            self._sticker_rows.insert(0, row)
        else:
            self._sticker_layout.addWidget(row)
            self._sticker_rows.append(row)

    def _on_emoji_deleted(self, asset_id: int) -> None:
        for row in self._emoji_rows:
            if row.asset_id == asset_id:
                row.deleteLater()
                self._emoji_rows.remove(row)
                break

    def _on_sticker_deleted(self, asset_id: int) -> None:
        for row in self._sticker_rows:
            if row.asset_id == asset_id:
                row.deleteLater()
                self._sticker_rows.remove(row)
                break

    @asyncSlot()
    async def _on_upload_emoji(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Emoji Image",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp)",
        )
        if not path:
            return
        state = AppState.instance()
        if state.client is None:
            return
        self._emoji_upload_btn.setEnabled(False)
        set_status(self._emoji_status, "uploading...", "info")
        try:
            from pathlib import Path

            name = Path(path).stem
            result = await state.client.emoji.create_emoji(name, path)
            self._add_emoji_row(result, prepend=True)
            set_status(self._emoji_status, "", "info")
        except Exception as exc:
            log.error("Failed to upload emoji: %s", exc)
            set_status(self._emoji_status, str(exc)[:30], "error")
        finally:
            self._emoji_upload_btn.setEnabled(True)

    @asyncSlot()
    async def _on_upload_sticker(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Sticker Image",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp)",
        )
        if not path:
            return
        state = AppState.instance()
        if state.client is None:
            return
        self._sticker_upload_btn.setEnabled(False)
        set_status(self._sticker_status, "uploading...", "info")
        try:
            from pathlib import Path

            name = Path(path).stem
            result = await state.client.emoji.create_sticker(name, path)
            self._add_sticker_row(result, prepend=True)
            set_status(self._sticker_status, "", "info")
        except Exception as exc:
            log.error("Failed to upload sticker: %s", exc)
            set_status(self._sticker_status, str(exc)[:30], "error")
        finally:
            self._sticker_upload_btn.setEnabled(True)


# -- Overview Page -----------------------------------------------------------


class _OverviewPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        state = AppState.instance()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(section_label("SERVER NAME", top_pad=12))
        self._name_input = QLineEdit(state.server_name)
        layout.addWidget(self._name_input)

        layout.addWidget(section_label("DESCRIPTION", top_pad=12))
        self._desc_input = QTextEdit()
        self._desc_input.setFixedHeight(100)
        self._desc_input.setPlaceholderText("A short description of your server...")
        layout.addWidget(self._desc_input)

        layout.addWidget(section_label("ICON URL", top_pad=12))
        self._icon_input = QLineEdit(state.server_icon or "")
        self._icon_input.setPlaceholderText("https://example.com/icon.png")
        layout.addWidget(self._icon_input)

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
            name = self._name_input.text().strip() or None
            desc = self._desc_input.toPlainText().strip() or None
            icon = self._icon_input.text().strip() or None
            result = await state.client.server.update(
                name=name,
                description=desc,
                icon=icon,
            )
            state.server_name = result.name
            state.server_icon = result.icon
            set_status(self._status, "saved", "success")
        except Exception as exc:
            log.error("Failed to save server settings: %s", exc)
            set_status(self._status, str(exc), "error")
        finally:
            self._save_btn.setEnabled(True)


# -- Roles Page --------------------------------------------------------------


class _RoleButton(QPushButton):
    """Selectable role button in the left list, matching channel settings style."""

    def __init__(self, role_id: int, name: str, color_int: int | None) -> None:
        super().__init__(name)
        self.role_id = role_id
        c = AppState.instance().theme.colors
        text_color = role_color_for_int(color_int) if color_int else c.text_secondary
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


class _RoleEditPanel(QWidget):
    """Inline panel for editing a single role."""

    role_saved = Signal()
    role_deleted = Signal()

    def __init__(self) -> None:
        super().__init__()
        c = AppState.instance().theme.colors
        self._role_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(4)

        # Empty state
        self._empty = QLabel("Select a role to edit")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet(
            f"color: {c.text_dim}; font-size: 12px; border: none; padding: 40px 0;"
        )
        layout.addWidget(self._empty)

        # Edit form (hidden until a role is selected)
        self._form = QWidget()
        form_layout = QVBoxLayout(self._form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(4)

        form_layout.addWidget(section_label("ROLE NAME", top_pad=12))
        self._name_input = QLineEdit()
        form_layout.addWidget(self._name_input)

        # Color row: label + input + preview swatch
        form_layout.addWidget(section_label("COLOR", top_pad=12))
        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        self._color_input = QLineEdit()
        self._color_input.setPlaceholderText("#ff5733")
        self._color_input.setFixedWidth(120)
        self._color_input.textChanged.connect(self._on_color_preview)
        color_row.addWidget(self._color_input)
        self._color_swatch = QWidget()
        self._color_swatch.setFixedSize(24, 24)
        self._color_swatch.setStyleSheet(
            f"background-color: {c.text_dim}; border-radius: 12px;"
        )
        color_row.addWidget(self._color_swatch)
        color_row.addStretch()
        form_layout.addLayout(color_row)

        form_layout.addWidget(section_label("PERMISSIONS", top_pad=12))

        # Single-column permission rows inside a scroll area
        self._perm_checks: dict[str, tuple[QCheckBox, int]] = {}
        perms_list = [
            ("Administrator", ADMINISTRATOR),
            ("Manage Server", MANAGE_SERVER),
            ("Manage Roles", MANAGE_ROLES),
            ("Manage Spaces", MANAGE_SPACES),
            ("Manage Messages", MANAGE_MESSAGES),
            ("Manage Emoji", MANAGE_EMOJI),
            ("Manage Webhooks", MANAGE_WEBHOOKS),
            ("Manage Nicknames", MANAGE_NICKNAMES),
            ("Manage 2FA", MANAGE_2FA),
            ("Manage Reports", MANAGE_REPORTS),
            ("Kick Members", KICK_MEMBERS),
            ("Ban Members", BAN_MEMBERS),
            ("View Spaces", VIEW_SPACE),
            ("Send Messages", SEND_MESSAGES),
            ("Send Embeds", SEND_EMBEDS),
            ("Attach Files", ATTACH_FILES),
            ("Add Reactions", ADD_REACTIONS),
            ("Read History", READ_HISTORY),
            ("Mention Everyone", MENTION_EVERYONE),
            ("Create Invites", CREATE_INVITES),
            ("Change Nickname", CHANGE_NICKNAME),
            ("View Audit Log", VIEW_AUDIT_LOG),
            ("View Reports", VIEW_REPORTS),
            ("Connect", CONNECT),
            ("Speak", SPEAK),
            ("Video", VIDEO),
            ("Stream", STREAM),
            ("Priority Speaker", PRIORITY_SPEAKER),
            ("Stage Moderator", STAGE_MODERATOR),
            ("Mute Members", MUTE_MEMBERS),
            ("Deafen Members", DEAFEN_MEMBERS),
            ("Move Members", MOVE_MEMBERS),
            ("Create Threads", CREATE_THREADS),
            ("Manage Threads", MANAGE_THREADS),
            ("Send in Threads", SEND_IN_THREADS),
        ]

        perm_scroll = QScrollArea()
        perm_scroll.setWidgetResizable(True)
        perm_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        perm_scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: transparent; }}"
            f"QScrollBar:vertical {{ width: 6px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {c.accent_dim}; "
            f"border-radius: 3px; min-height: 20px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )
        perm_container = QWidget()
        perm_container.setStyleSheet("background: transparent; border: none;")
        perm_layout = QVBoxLayout(perm_container)
        perm_layout.setContentsMargins(0, 0, 0, 0)
        perm_layout.setSpacing(2)

        for label, bit in perms_list:
            row = QHBoxLayout()
            row.setSpacing(8)
            perm_label = QLabel(label)
            perm_label.setFixedWidth(130)
            perm_label.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 11px; border: none;"
            )
            row.addWidget(perm_label)
            cb = QCheckBox()
            cb.setStyleSheet(
                f"QCheckBox {{ border: none; spacing: 4px; }}"
                f"QCheckBox::indicator {{ width: 16px; height: 16px; "
                f"border: 1px solid {c.border_bright}; border-radius: 3px; "
                f"background: {c.bg_input}; }}"
                f"QCheckBox::indicator:checked {{ background: {c.accent_dim}; "
                f"border-color: {c.accent}; }}"
            )
            row.addWidget(cb)
            row.addStretch()
            perm_layout.addLayout(row)
            self._perm_checks[label] = (cb, bit)

        perm_layout.addStretch()
        perm_scroll.setWidget(perm_container)
        form_layout.addWidget(perm_scroll, stretch=1)

        form_layout.addSpacing(8)
        self._status = status_label()
        form_layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        self._save_btn = action_button("[ SAVE ]")
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)
        self._delete_btn = danger_button("[ DELETE ]")
        self._delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._delete_btn)
        form_layout.addLayout(btn_row)

        self._form.hide()
        layout.addWidget(self._form, stretch=1)

    def load_role(self, role_id: int) -> None:
        state = AppState.instance()
        role = state._roles.get(role_id)
        if role is None:
            return
        self._role_id = role_id
        self._empty.hide()
        self._form.show()
        self._name_input.setText(role.name)
        hex_c = role_color_for_int(role.color) or ""
        self._color_input.setText(hex_c)
        self._on_color_preview(hex_c)
        perms = role.permissions or 0
        for _label, (cb, bit) in self._perm_checks.items():
            cb.setChecked(bool(perms & bit))
        set_status(self._status, "", "info")

    def clear(self) -> None:
        self._role_id = None
        self._form.hide()
        self._empty.show()

    def _on_color_preview(self, text: str) -> None:
        c = AppState.instance().theme.colors
        cleaned = text.strip()
        if not cleaned.startswith("#"):
            cleaned = "#" + cleaned
        if len(cleaned) == 7:
            self._color_swatch.setStyleSheet(
                f"background-color: {cleaned}; border-radius: 12px;"
            )
        else:
            self._color_swatch.setStyleSheet(
                f"background-color: {c.text_dim}; border-radius: 12px;"
            )

    def _collect_permissions(self) -> int:
        result = 0
        for _label, (cb, bit) in self._perm_checks.items():
            if cb.isChecked():
                result |= bit
        return result

    def _parse_color(self) -> int | None:
        text = self._color_input.text().strip().lstrip("#")
        if not text:
            return None
        try:
            return int(text, 16)
        except ValueError:
            return None

    @asyncSlot()
    async def _on_save(self) -> None:
        state = AppState.instance()
        if state.client is None or self._role_id is None:
            return
        self._save_btn.setEnabled(False)
        set_status(self._status, "saving...", "info")
        try:
            result = await state.client.roles.update(
                self._role_id,
                name=self._name_input.text().strip() or None,
                color=self._parse_color(),
                permissions=self._collect_permissions(),
            )
            state._roles[result.role_id] = result
            set_status(self._status, "saved", "success")
            self.role_saved.emit()
        except Exception as exc:
            log.error("Failed to save role %d: %s", self._role_id, exc)
            show_toast(_friendly_error(exc))
        finally:
            self._save_btn.setEnabled(True)

    @asyncSlot()
    async def _on_delete(self) -> None:
        state = AppState.instance()
        if state.client is None or self._role_id is None:
            return
        self._delete_btn.setEnabled(False)
        set_status(self._status, "deleting...", "info")
        try:
            await state.client.roles.delete(self._role_id)
            state._roles.pop(self._role_id, None)
            set_status(self._status, "deleted", "success")
            self._role_id = None
            self.role_deleted.emit()
        except Exception as exc:
            log.error("Failed to delete role %d: %s", self._role_id, exc)
            show_toast(_friendly_error(exc))
        finally:
            self._delete_btn.setEnabled(True)


class _RolesPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        c = AppState.instance().theme.colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar: section label + create button
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addWidget(section_label("ROLES", top_pad=12))
        top_row.addStretch()
        self._create_status = status_label()
        self._create_status.setFixedWidth(80)
        top_row.addWidget(self._create_status)
        layout.addLayout(top_row)

        layout.addSpacing(4)

        # Split: role list on the left | separator | edit panel on the right
        split = QHBoxLayout()
        split.setSpacing(0)

        # Left: role list in scroll area + new button at bottom
        left_panel = QWidget()
        left_panel.setFixedWidth(160)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(2)

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
        self._role_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        role_scroll.setWidget(role_container)
        left_layout.addWidget(role_scroll, stretch=1)

        self._create_btn = QPushButton("[ + NEW ]")
        self._create_btn.setFixedHeight(30)
        self._create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {c.border}; "
            f"color: {c.text_secondary}; border-radius: 4px; font-size: 12px; font-weight: 500; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; "
            f"border-color: {c.border_bright}; color: {c.text_primary}; }}"
            f"QPushButton:pressed {{ background-color: {c.bg_active}; }}"
            f"QPushButton:disabled {{ color: {c.text_dim}; border-color: {c.border}; }}"
        )
        self._create_btn.clicked.connect(self._on_create)
        left_layout.addWidget(self._create_btn)

        split.addWidget(left_panel)

        # Vertical separator
        sep = QWidget()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background-color: {c.border};")
        split.addWidget(sep)

        # Right: edit panel
        self._edit_panel = _RoleEditPanel()
        self._edit_panel.role_saved.connect(self._refresh_list)
        self._edit_panel.role_deleted.connect(self._on_role_deleted)
        split.addWidget(self._edit_panel, stretch=1)

        layout.addLayout(split, stretch=1)

        self._role_buttons: list[_RoleButton] = []
        self._active_role_id: int | None = None
        self._refresh_list()

    def _refresh_list(self) -> None:
        for btn in self._role_buttons:
            btn.deleteLater()
        self._role_buttons.clear()

        state = AppState.instance()
        roles = sorted(state._roles.values(), key=lambda r: r.position, reverse=True)
        for role in roles:
            btn = _RoleButton(role.role_id, role.name, role.color)
            btn.clicked.connect(lambda checked, rid=role.role_id: self._on_role_clicked(rid))
            self._role_list_layout.addWidget(btn)
            self._role_buttons.append(btn)
            if role.role_id == self._active_role_id:
                btn.set_active(True)

    def _on_role_clicked(self, role_id: int) -> None:
        self._active_role_id = role_id
        for btn in self._role_buttons:
            btn.set_active(btn.role_id == role_id)
        self._edit_panel.load_role(role_id)

    def _on_role_deleted(self) -> None:
        self._active_role_id = None
        self._edit_panel.clear()
        self._refresh_list()

    @asyncSlot()
    async def _on_create(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        self._create_btn.setEnabled(False)
        set_status(self._create_status, "creating...", "info")
        try:
            result = await state.client.roles.create("New Role")
            state._roles[result.role_id] = result
            set_status(self._create_status, "", "info")
            self._active_role_id = result.role_id
            self._refresh_list()
            self._edit_panel.load_role(result.role_id)
        except Exception as exc:
            log.error("Failed to create role: %s", exc)
            set_status(self._create_status, str(exc)[:30], "error")
        finally:
            self._create_btn.setEnabled(True)


# -- Members Page ------------------------------------------------------------


class _MemberRow(QWidget):
    def __init__(self, user_id: int) -> None:
        super().__init__()
        self.user_id = user_id
        self.setFixedHeight(36)

        state = AppState.instance()
        c = state.theme.colors

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 2, 8, 2)
        row.setSpacing(10)

        # Avatar circle
        name = state.get_display_name(user_id)
        row.addWidget(AvatarWidget(user_id, size=24, parent=self))

        # Name
        name_hex = state.get_role_color(user_id) or c.text_secondary
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color: {name_hex}; font-size: 12px; border: none;")
        row.addWidget(name_lbl, stretch=1)

        # Status label (inline feedback)
        self._status = status_label()
        self._status.setFixedWidth(70)
        self._status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self._status)

        # Action buttons
        btn_style = (
            "QPushButton {{ color: {color}; font-size: 10px; font-weight: 600; "
            "border: 1px solid {color}; border-radius: 3px; padding: 2px 8px; "
            "background: transparent; }}"
            "QPushButton:hover {{ background-color: {color}; color: {bg}; }}"
            "QPushButton:disabled {{ color: {muted}; border-color: {muted}; }}"
        )

        self._kick_btn = QPushButton("KICK")
        self._kick_btn.setFixedHeight(22)
        self._kick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._kick_btn.setStyleSheet(
            btn_style.format(
                color=c.status_warning,
                bg=c.bg_deep,
                muted=c.text_dim,
            )
        )
        self._kick_btn.clicked.connect(self._on_kick)
        row.addWidget(self._kick_btn)

        self._ban_btn = QPushButton("BAN")
        self._ban_btn.setFixedHeight(22)
        self._ban_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ban_btn.setStyleSheet(
            btn_style.format(
                color=c.status_danger,
                bg=c.bg_deep,
                muted=c.text_dim,
            )
        )
        self._ban_btn.clicked.connect(self._on_ban)
        row.addWidget(self._ban_btn)

        # Roles button
        roles_style = (
            f"QPushButton {{ color: {c.accent}; font-size: 10px; font-weight: 600; "
            f"border: 1px solid {c.accent}; border-radius: 3px; padding: 2px 8px; "
            f"background: transparent; }}"
            f"QPushButton:hover {{ background-color: {c.accent}; color: {c.bg_deep}; }}"
            f"QPushButton:disabled {{ color: {c.text_dim}; border-color: {c.text_dim}; }}"
        )
        self._roles_btn = QPushButton("ROLES")
        self._roles_btn.setFixedHeight(22)
        self._roles_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._roles_btn.setStyleSheet(roles_style)
        self._roles_btn.clicked.connect(self._on_roles)
        row.addWidget(self._roles_btn)

    def enterEvent(self, event) -> None:  # noqa: ANN001
        c = AppState.instance().theme.colors
        self.setStyleSheet(f"background-color: {c.bg_hover}; border-radius: 4px;")

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        self.setStyleSheet("background: transparent;")

    @asyncSlot()
    async def _on_kick(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        self._kick_btn.setEnabled(False)
        try:
            await state.client.members.remove(self.user_id)
            log.info("Kicked member %d", self.user_id)
            set_status(self._status, "kicked", "success")
        except Exception as exc:
            log.error("Failed to kick member %d: %s", self.user_id, exc)
            show_toast(_friendly_error(exc))
        finally:
            self._kick_btn.setEnabled(True)

    @asyncSlot()
    async def _on_ban(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        self._ban_btn.setEnabled(False)
        try:
            await state.client.members.ban(self.user_id)
            log.info("Banned member %d", self.user_id)
            set_status(self._status, "banned", "success")
        except Exception as exc:
            log.error("Failed to ban member %d: %s", self.user_id, exc)
            show_toast(_friendly_error(exc))
        finally:
            self._ban_btn.setEnabled(True)

    def _on_roles(self) -> None:
        state = AppState.instance()
        member = state._members.get(self.user_id)
        if member is None:
            return
        popup = _RoleAssignPopup(self.user_id, parent=self.window())
        popup.exec()


class _RoleCheckRow(QWidget):
    """Single role checkbox row in the assign popup."""

    toggled = Signal(int, bool)  # role_id, checked

    def __init__(
        self, role_id: int, name: str, color_int: int | None, checked: bool
    ) -> None:
        super().__init__()
        self.role_id = role_id
        c = AppState.instance().theme.colors
        hex_color = role_color_for_int(color_int) or c.text_dim

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 2, 8, 2)
        row.setSpacing(8)

        # Color dot
        dot = QLabel("\u25cf")
        dot.setFixedWidth(14)
        dot.setStyleSheet(f"color: {hex_color}; font-size: 14px; border: none;")
        row.addWidget(dot)

        # Checkbox
        self._cb = QCheckBox(name)
        self._cb.setChecked(checked)
        self._cb.setStyleSheet(
            f"QCheckBox {{ color: {c.text_secondary}; font-size: 12px; "
            f"border: none; spacing: 6px; }}"
            f"QCheckBox::indicator {{ width: 16px; height: 16px; "
            f"border: 1px solid {c.border_bright}; border-radius: 3px; "
            f"background: {c.bg_panel}; }}"
            f"QCheckBox::indicator:checked {{ background: {c.accent_dim}; "
            f"border-color: {c.accent}; }}"
        )
        self._cb.toggled.connect(
            lambda state, rid=role_id: self.toggled.emit(rid, state)
        )
        row.addWidget(self._cb, stretch=1)

    def set_checked(self, checked: bool) -> None:
        self._cb.blockSignals(True)
        self._cb.setChecked(checked)
        self._cb.blockSignals(False)


class _RoleAssignPopup(QDialog):
    """Popup for assigning/revoking roles on a member."""

    def __init__(self, user_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._user_id = user_id
        state = AppState.instance()
        c = state.theme.colors

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(280, 320)
        self.setStyleSheet(
            f"_RoleAssignPopup {{ background-color: {c.bg_panel}; "
            f"border: 1px solid {c.border_bright}; border-radius: 6px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Title
        display_name = state.get_display_name(user_id)
        title = QLabel(f"Roles for {display_name}")
        title.setStyleSheet(
            f"color: {c.text_primary}; font-size: 13px; font-weight: 600; border: none;"
        )
        layout.addWidget(title)

        layout.addSpacing(4)

        # Scrollable role list
        scroll, _container, self._roles_layout = _make_scroll_area()
        layout.addWidget(scroll, stretch=1)

        self._check_rows: list[_RoleCheckRow] = []
        member = state._members.get(user_id)
        member_role_ids = member.role_ids if member else []

        roles = sorted(state._roles.values(), key=lambda r: r.position, reverse=True)
        for role in roles:
            checked = role.role_id in member_role_ids
            row = _RoleCheckRow(role.role_id, role.name, role.color, checked)
            row.toggled.connect(self._on_toggle)
            self._roles_layout.addWidget(row)
            self._check_rows.append(row)

        self._status = status_label()
        layout.addWidget(self._status)

    @asyncSlot(int, bool)
    async def _on_toggle(self, role_id: int, checked: bool) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        # Find the row for potential revert
        row = next((r for r in self._check_rows if r.role_id == role_id), None)
        try:
            if checked:
                await state.client.roles.assign(self._user_id, role_id)
                # Update cache
                member = state._members.get(self._user_id)
                if member and role_id not in member.role_ids:
                    member.role_ids.append(role_id)
            else:
                await state.client.roles.revoke(self._user_id, role_id)
                # Update cache
                member = state._members.get(self._user_id)
                if member and role_id in member.role_ids:
                    member.role_ids.remove(role_id)
        except Exception as exc:
            log.error(
                "Failed to %s role %d for user %d: %s",
                "assign" if checked else "revoke",
                role_id,
                self._user_id,
                exc,
            )
            show_toast(_friendly_error(exc))
            # Revert checkbox
            if row:
                row.set_checked(not checked)


class _BanRow(QWidget):
    def __init__(self, user_id: int, reason: str | None) -> None:
        super().__init__()
        self.user_id = user_id
        self.setFixedHeight(34)
        c = AppState.instance().theme.colors

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 2, 8, 2)
        row.setSpacing(10)

        # Banned icon
        icon_btn = QLabel()
        icon_btn.setFixedSize(18, 18)
        icon_btn.setPixmap(
            tinted_icon(
                _ICONS_DIR / "account-cancel.svg", c.status_danger, size=16
            ).pixmap(16, 16)
        )
        icon_btn.setStyleSheet("border: none;")
        row.addWidget(icon_btn)

        lbl = QLabel(f"User {user_id}")
        lbl.setStyleSheet(f"color: {c.text_secondary}; font-size: 12px; border: none;")
        row.addWidget(lbl)

        if reason:
            reason_lbl = QLabel(f"\u2014 {reason}")
            reason_lbl.setStyleSheet(
                f"color: {c.text_dim}; font-size: 11px; border: none;"
            )
            row.addWidget(reason_lbl, stretch=1)
        else:
            row.addStretch()

        self._status = status_label()
        self._status.setFixedWidth(70)
        self._status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self._status)

        self._unban_btn = QPushButton("UNBAN")
        self._unban_btn.setFixedHeight(22)
        self._unban_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._unban_btn.setStyleSheet(
            f"QPushButton {{ color: {c.accent}; font-size: 10px; font-weight: 600; "
            f"border: 1px solid {c.accent_dim}; border-radius: 3px; "
            f"padding: 2px 8px; background: transparent; }}"
            f"QPushButton:hover {{ background-color: {c.accent}; color: {c.bg_deep}; }}"
        )
        self._unban_btn.clicked.connect(self._on_unban)
        row.addWidget(self._unban_btn)

    def enterEvent(self, event) -> None:  # noqa: ANN001
        c = AppState.instance().theme.colors
        self.setStyleSheet(f"background-color: {c.bg_hover}; border-radius: 4px;")

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        self.setStyleSheet("background: transparent;")

    @asyncSlot()
    async def _on_unban(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        self._unban_btn.setEnabled(False)
        try:
            await state.client.members.unban(self.user_id)
            log.info("Unbanned member %d", self.user_id)
            set_status(self._status, "unbanned", "success")
        except Exception as exc:
            log.error("Failed to unban member %d: %s", self.user_id, exc)
            set_status(self._status, str(exc)[:20], "error")
        finally:
            self._unban_btn.setEnabled(True)


class _MembersPage(QWidget):
    def __init__(self) -> None:
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("\u2315  filter members...")
        self._search.setFixedHeight(30)
        self._search.textChanged.connect(self._on_filter)
        layout.addWidget(self._search)

        layout.addSpacing(4)

        # Members section
        layout.addWidget(section_label("MEMBERS", top_pad=12))
        self._member_scroll, self._member_container, self._member_layout = (
            _make_scroll_area()
        )
        layout.addWidget(self._member_scroll, stretch=1)

        layout.addWidget(separator())

        # Bans section
        layout.addWidget(section_label("BANS", top_pad=12))
        self._ban_scroll, self._ban_container, self._ban_layout = _make_scroll_area()
        self._ban_scroll.setFixedHeight(130)
        layout.addWidget(self._ban_scroll)

        self._member_rows: list[_MemberRow] = []
        self._ban_rows: list[_BanRow] = []

        self._populate_members()
        self._load_bans()

    def _populate_members(self, filter_text: str = "") -> None:
        for row in self._member_rows:
            row.deleteLater()
        self._member_rows.clear()

        state = AppState.instance()
        ft = filter_text.lower()
        for uid, _member in sorted(
            state._members.items(), key=lambda x: state.get_display_name(x[0]).lower()
        ):
            name = state.get_display_name(uid).lower()
            if ft and ft not in name:
                continue
            row = _MemberRow(uid)
            self._member_layout.addWidget(row)
            self._member_rows.append(row)

    def _on_filter(self, text: str) -> None:
        self._populate_members(text)

    @asyncSlot()
    async def _load_bans(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        try:
            bans = await state.client.members.list_bans()
            for ban in bans.items:
                uid = ban.user_id
                reason = getattr(ban, "reason", None)
                row = _BanRow(uid, reason)
                self._ban_layout.addWidget(row)
                self._ban_rows.append(row)
        except Exception:
            log.warning("Failed to load ban list", exc_info=True)


# -- Limits Page -------------------------------------------------------------


class _LimitsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        c = AppState.instance().theme.colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(section_label("SERVER LIMITS", top_pad=12))

        self._scroll, self._fields_container, self._fields_layout = _make_scroll_area()
        self._fields_layout.setSpacing(4)
        layout.addWidget(self._scroll, stretch=1)

        self._fields: dict[str, QLineEdit] = {}

        layout.addSpacing(8)
        self._status = status_label()
        layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        self._save_btn = action_button("[ SAVE ]")
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)
        layout.addLayout(btn_row)

        self._load_limits()

    @asyncSlot()
    async def _load_limits(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        c = state.theme.colors
        try:
            limits = await state.client.server.get_limits()
            if isinstance(limits, dict):
                data = limits
            else:
                data = limits.model_dump() if hasattr(limits, "model_dump") else {}
            for key, value in data.items():
                # Each limit as a styled row: label on left, input on right
                row_w = QWidget()
                row_w.setFixedHeight(36)
                row_w.setStyleSheet(
                    f"background-color: {c.bg_panel}; border-radius: 4px;"
                )
                row_l = QHBoxLayout(row_w)
                row_l.setContentsMargins(12, 4, 8, 4)
                row_l.setSpacing(8)

                lbl = QLabel(key.replace("_", " "))
                lbl.setStyleSheet(
                    f"color: {c.text_secondary}; font-size: 12px; border: none;"
                )
                row_l.addWidget(lbl, stretch=1)

                inp = QLineEdit(str(value))
                inp.setFixedWidth(100)
                inp.setAlignment(Qt.AlignmentFlag.AlignRight)
                inp.setStyleSheet(
                    f"background-color: {c.bg_input}; color: {c.text_primary}; "
                    f"border: 1px solid {c.border}; border-radius: 3px; "
                    f"padding: 2px 8px; font-size: 12px;"
                )
                row_l.addWidget(inp)

                self._fields_layout.addWidget(row_w)
                self._fields[key] = inp
        except Exception as exc:
            log.warning("Failed to load server limits: %s", exc)
            set_status(self._status, str(exc), "error")

    @asyncSlot()
    async def _on_save(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        self._save_btn.setEnabled(False)
        set_status(self._status, "saving...", "info")
        try:
            kwargs = {}
            for key, inp in self._fields.items():
                val = inp.text().strip()
                try:
                    kwargs[key] = int(val)
                except ValueError:
                    kwargs[key] = val
            await state.client.server.update_limits(**kwargs)
            set_status(self._status, "saved", "success")
        except Exception as exc:
            log.error("Failed to save server limits: %s", exc)
            set_status(self._status, str(exc), "error")
        finally:
            self._save_btn.setEnabled(True)


# -- Main Dialog -------------------------------------------------------------

_NAV_ITEMS = [
    ("Overview", "view-carousel.svg"),
    ("Roles", "account-group.svg"),
    ("Members", "account.svg"),
    ("Invites", "link-variant.svg"),
    ("Emoji && Stickers", "emoticon-outline.svg"),
    ("Limits", "gauge.svg"),
]


class ServerSettingsDialog(BaseSettingsDialog):
    """Frameless server settings dialog with sidebar navigation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("SERVER SETTINGS", _NAV_ITEMS, parent)

    def _build_pages(self) -> None:
        self._overview_page = _OverviewPage()
        self._roles_page = _RolesPage()
        self._members_page = _MembersPage()
        self._invites_page = _InvitesPage()
        self._emoji_stickers_page = _EmojiStickersPage()
        self._limits_page = _LimitsPage()

        for page in (
            self._overview_page,
            self._roles_page,
            self._members_page,
            self._invites_page,
            self._emoji_stickers_page,
            self._limits_page,
        ):
            self._add_page(page)
