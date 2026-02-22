"""Server settings dialog – frameless modal with sidebar navigation."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
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

from vox_sdk.permissions import (
    ADMINISTRATOR,
    BAN_MEMBERS,
    KICK_MEMBERS,
    MANAGE_MESSAGES,
    MANAGE_ROLES,
    MANAGE_SERVER,
    MANAGE_SPACES,
    SEND_MESSAGES,
    VIEW_SPACE,
)

from vox_client._frozen import ICONS_DIR as _ICONS_DIR
from vox_client.state import AppState
from vox_client.theme import role_color_for_int
from vox_client.widgets.avatar import AvatarWidget
from vox_client.widgets.base_settings_dialog import BaseSettingsDialog
from vox_client.widgets.icons import tinted_icon
from vox_client.widgets.ui_helpers import (
    action_button,
    danger_button,
    section_label,
    separator,
    set_status,
    status_label,
)


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
                name=name, description=desc, icon=icon,
            )
            state.server_name = result.name
            state.server_icon = result.icon
            set_status(self._status, "saved", "success")
        except Exception as exc:
            set_status(self._status, str(exc), "error")
        finally:
            self._save_btn.setEnabled(True)


# -- Roles Page --------------------------------------------------------------

class _RoleItem(QWidget):
    """Single role row in the scrollable list."""

    selected = pyqtSignal(int)

    def __init__(self, role_id: int, name: str, color_int: int | None) -> None:
        super().__init__()
        self.role_id = role_id
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)

        c = AppState.instance().theme.colors
        self._colors = c
        self._hex_color = role_color_for_int(color_int) or c.text_dim

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(10)

        # Color dot
        self._dot = QLabel("\u25cf")
        self._dot.setFixedWidth(14)
        self._dot.setStyleSheet(f"color: {self._hex_color}; font-size: 14px; border: none;")
        row.addWidget(self._dot)

        self._label = QLabel(name)
        self._label.setStyleSheet(f"color: {c.text_secondary}; font-size: 12px; border: none;")
        row.addWidget(self._label, stretch=1)

        self._update_style()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update_style()

    def _update_style(self) -> None:
        c = self._colors
        if self._active:
            self.setStyleSheet(f"background-color: {c.bg_active}; border-radius: 4px;")
            self._label.setStyleSheet(f"color: {c.text_primary}; font-size: 12px; border: none;")
        else:
            self.setStyleSheet("background: transparent; border-radius: 4px;")
            self._label.setStyleSheet(f"color: {c.text_secondary}; font-size: 12px; border: none;")

    def enterEvent(self, event) -> None:  # noqa: ANN001
        if not self._active:
            c = self._colors
            self.setStyleSheet(f"background-color: {c.bg_hover}; border-radius: 4px;")
            self._label.setStyleSheet(f"color: {c.text_primary}; font-size: 12px; border: none;")

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        if not self._active:
            self._update_style()

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        self.selected.emit(self.role_id)


class _RoleEditPanel(QWidget):
    """Inline panel for editing a single role."""

    role_saved = pyqtSignal()
    role_deleted = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        c = AppState.instance().theme.colors
        self._role_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 0, 0, 0)
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

        # Permission grid (2 columns)
        self._perm_checks: dict[str, tuple[QCheckBox, int]] = {}
        perms_list = [
            ("Administrator", ADMINISTRATOR),
            ("Manage Server", MANAGE_SERVER),
            ("Manage Roles", MANAGE_ROLES),
            ("Manage Spaces", MANAGE_SPACES),
            ("Manage Messages", MANAGE_MESSAGES),
            ("Kick Members", KICK_MEMBERS),
            ("Ban Members", BAN_MEMBERS),
            ("Send Messages", SEND_MESSAGES),
            ("View Spaces", VIEW_SPACE),
        ]
        perm_grid = QWidget()
        perm_grid.setStyleSheet("border: none;")
        grid_outer = QVBoxLayout(perm_grid)
        grid_outer.setContentsMargins(0, 0, 0, 0)
        grid_outer.setSpacing(2)

        # Lay out in 2-column rows
        for i in range(0, len(perms_list), 2):
            row_w = QHBoxLayout()
            row_w.setSpacing(16)
            for j in range(2):
                if i + j < len(perms_list):
                    label, bit = perms_list[i + j]
                    cb = QCheckBox(label)
                    cb.setStyleSheet(
                        f"QCheckBox {{ color: {c.text_secondary}; font-size: 11px; "
                        f"border: none; spacing: 6px; }}"
                        f"QCheckBox::indicator {{ width: 16px; height: 16px; "
                        f"border: 1px solid {c.border_bright}; border-radius: 3px; "
                        f"background: {c.bg_panel}; }}"
                        f"QCheckBox::indicator:checked {{ background: {c.accent_dim}; "
                        f"border-color: {c.accent}; }}"
                    )
                    row_w.addWidget(cb)
                    self._perm_checks[label] = (cb, bit)
            row_w.addStretch()
            grid_outer.addLayout(row_w)

        form_layout.addWidget(perm_grid)

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

        form_layout.addStretch()
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
            set_status(self._status, str(exc), "error")
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
            set_status(self._status, str(exc), "error")
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
        self._create_btn = action_button("[ + NEW ]", width=90)
        self._create_btn.clicked.connect(self._on_create)
        top_row.addWidget(self._create_btn)
        layout.addLayout(top_row)

        layout.addSpacing(4)

        # Split: role list on the left | edit panel on the right
        split = QHBoxLayout()
        split.setSpacing(0)

        # Left: role list in scroll area
        left = QWidget()
        left.setFixedWidth(170)
        left.setStyleSheet(f"background-color: {c.bg_panel}; border-radius: 6px;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 6, 4, 6)
        left_layout.setSpacing(0)

        self._role_scroll, self._role_list_container, self._role_list_layout = _make_scroll_area()
        left_layout.addWidget(self._role_scroll)
        split.addWidget(left)

        # Right: edit panel
        self._edit_panel = _RoleEditPanel()
        self._edit_panel.role_saved.connect(self._refresh_list)
        self._edit_panel.role_deleted.connect(self._on_role_deleted)
        split.addWidget(self._edit_panel, stretch=1)

        layout.addLayout(split, stretch=1)

        self._role_items: list[_RoleItem] = []
        self._active_role_id: int | None = None
        self._refresh_list()

    def _refresh_list(self) -> None:
        for item in self._role_items:
            item.deleteLater()
        self._role_items.clear()

        state = AppState.instance()
        roles = sorted(state._roles.values(), key=lambda r: r.position, reverse=True)
        for role in roles:
            item = _RoleItem(role.role_id, role.name, role.color)
            item.selected.connect(self._on_role_clicked)
            self._role_list_layout.addWidget(item)
            self._role_items.append(item)
            if role.role_id == self._active_role_id:
                item.set_active(True)

    def _on_role_clicked(self, role_id: int) -> None:
        self._active_role_id = role_id
        for item in self._role_items:
            item.set_active(item.role_id == role_id)
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
        self._status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
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
        self._kick_btn.setStyleSheet(btn_style.format(
            color=c.status_warning, bg=c.bg_deep, muted=c.text_dim,
        ))
        self._kick_btn.clicked.connect(self._on_kick)
        row.addWidget(self._kick_btn)

        self._ban_btn = QPushButton("BAN")
        self._ban_btn.setFixedHeight(22)
        self._ban_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ban_btn.setStyleSheet(btn_style.format(
            color=c.status_danger, bg=c.bg_deep, muted=c.text_dim,
        ))
        self._ban_btn.clicked.connect(self._on_ban)
        row.addWidget(self._ban_btn)

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
            set_status(self._status, "kicked", "success")
        except Exception as exc:
            set_status(self._status, str(exc)[:20], "error")
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
            set_status(self._status, "banned", "success")
        except Exception as exc:
            set_status(self._status, str(exc)[:20], "error")
        finally:
            self._ban_btn.setEnabled(True)


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
            tinted_icon(_ICONS_DIR / "account-cancel.svg", c.status_danger, size=16).pixmap(16, 16)
        )
        icon_btn.setStyleSheet("border: none;")
        row.addWidget(icon_btn)

        lbl = QLabel(f"User {user_id}")
        lbl.setStyleSheet(f"color: {c.text_secondary}; font-size: 12px; border: none;")
        row.addWidget(lbl)

        if reason:
            reason_lbl = QLabel(f"\u2014 {reason}")
            reason_lbl.setStyleSheet(f"color: {c.text_dim}; font-size: 11px; border: none;")
            row.addWidget(reason_lbl, stretch=1)
        else:
            row.addStretch()

        self._status = status_label()
        self._status.setFixedWidth(70)
        self._status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
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
            set_status(self._status, "unbanned", "success")
        except Exception as exc:
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
        self._member_scroll, self._member_container, self._member_layout = _make_scroll_area()
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
        for uid, _member in sorted(state._members.items(), key=lambda x: state.get_display_name(x[0]).lower()):
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
            pass


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
            set_status(self._status, str(exc), "error")
        finally:
            self._save_btn.setEnabled(True)


# -- Main Dialog -------------------------------------------------------------

_NAV_ITEMS = [
    ("Overview", "view-carousel.svg"),
    ("Roles", "account-group.svg"),
    ("Members", "account.svg"),
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
        self._limits_page = _LimitsPage()

        for page in (self._overview_page, self._roles_page, self._members_page, self._limits_page):
            self._add_page(page)
