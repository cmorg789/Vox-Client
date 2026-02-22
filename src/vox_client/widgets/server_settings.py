"""Server settings dialog – frameless modal with sidebar navigation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
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


def _tinted_icon(svg_path: Path, color: str, size: int = 16) -> QIcon:
    """Load an SVG and return a QIcon with paths filled in *color*."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPainter

    svg_text = svg_path.read_text()
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


# -- Helpers -----------------------------------------------------------------

def _section_label(text: str) -> QLabel:
    c = AppState.instance().theme.colors
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {c.text_dim}; font-size: 10px; font-weight: 600; "
        f"letter-spacing: 1px; padding: 12px 0 6px 0; border: none;"
    )
    return lbl


def _field_label(text: str) -> QLabel:
    c = AppState.instance().theme.colors
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color: {c.text_dim}; font-size: 11px; font-weight: 600; "
        f"letter-spacing: 0.5px; padding: 2px 0 2px 0; border: none;"
    )
    return lbl


def _status_label() -> QLabel:
    lbl = QLabel("")
    lbl.setFixedHeight(18)
    lbl.setStyleSheet("border: none; padding: 0;")
    return lbl


def _set_status(label: QLabel, text: str, kind: str = "info") -> None:
    c = AppState.instance().theme.colors
    color_map = {"info": c.text_dim, "error": c.status_danger, "success": c.status_success}
    color = color_map.get(kind, c.text_dim)
    label.setText(text)
    label.setStyleSheet(f"color: {color}; border: none; padding: 0; font-size: 11px;")


def _action_button(text: str, width: int = 110) -> QPushButton:
    c = AppState.instance().theme.colors
    btn = QPushButton(text)
    btn.setFixedHeight(30)
    btn.setFixedWidth(width)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(
        f"QPushButton {{ background-color: {c.accent_dim}; border: 1px solid {c.accent}; "
        f"color: {c.accent_bright}; border-radius: 4px; padding: 6px 16px; font-weight: 500; }}"
        f"QPushButton:hover {{ background-color: {c.accent}; border-color: {c.accent_bright}; color: {c.text_on_accent}; }}"
        f"QPushButton:pressed {{ background-color: {c.accent_dim}; }}"
        f"QPushButton:disabled {{ color: {c.text_dim}; border-color: {c.border}; background: transparent; }}"
    )
    return btn


def _danger_button(text: str, width: int = 110) -> QPushButton:
    c = AppState.instance().theme.colors
    btn = QPushButton(text)
    btn.setFixedHeight(30)
    btn.setFixedWidth(width)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(
        f"QPushButton {{ background-color: {c.status_danger_dim}; "
        f"border: 1px solid {c.status_danger}; color: {c.status_danger}; "
        f"border-radius: 4px; padding: 4px 12px; font-weight: 500; }}"
        f"QPushButton:hover {{ background-color: {c.status_danger}; color: {c.text_on_accent}; }}"
        f"QPushButton:disabled {{ color: {c.text_dim}; border-color: {c.border}; "
        f"background: transparent; }}"
    )
    return btn


def _separator() -> QFrame:
    c = AppState.instance().theme.colors
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet(f"background-color: {c.border}; border: none;")
    return line


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
        c = state.theme.colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(_section_label("SERVER NAME"))
        self._name_input = QLineEdit(state.server_name)
        layout.addWidget(self._name_input)

        layout.addWidget(_section_label("DESCRIPTION"))
        self._desc_input = QTextEdit()
        self._desc_input.setFixedHeight(100)
        self._desc_input.setPlaceholderText("A short description of your server...")
        layout.addWidget(self._desc_input)

        layout.addWidget(_section_label("ICON URL"))
        self._icon_input = QLineEdit(state.server_icon or "")
        self._icon_input.setPlaceholderText("https://example.com/icon.png")
        layout.addWidget(self._icon_input)

        layout.addSpacing(12)

        self._status = _status_label()
        layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        self._save_btn = _action_button("[ SAVE ]")
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
        _set_status(self._status, "saving...", "info")
        try:
            name = self._name_input.text().strip() or None
            desc = self._desc_input.toPlainText().strip() or None
            icon = self._icon_input.text().strip() or None
            result = await state.client.server.update(
                name=name, description=desc, icon=icon,
            )
            state.server_name = result.name
            state.server_icon = result.icon
            _set_status(self._status, "saved", "success")
        except Exception as exc:
            _set_status(self._status, str(exc), "error")
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

        form_layout.addWidget(_section_label("ROLE NAME"))
        self._name_input = QLineEdit()
        form_layout.addWidget(self._name_input)

        # Color row: label + input + preview swatch
        form_layout.addWidget(_section_label("COLOR"))
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

        form_layout.addWidget(_section_label("PERMISSIONS"))

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
        self._status = _status_label()
        form_layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        self._save_btn = _action_button("[ SAVE ]")
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)
        self._delete_btn = _danger_button("[ DELETE ]")
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
        _set_status(self._status, "", "info")

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
        _set_status(self._status, "saving...", "info")
        try:
            result = await state.client.roles.update(
                self._role_id,
                name=self._name_input.text().strip() or None,
                color=self._parse_color(),
                permissions=self._collect_permissions(),
            )
            state._roles[result.role_id] = result
            _set_status(self._status, "saved", "success")
            self.role_saved.emit()
        except Exception as exc:
            _set_status(self._status, str(exc), "error")
        finally:
            self._save_btn.setEnabled(True)

    @asyncSlot()
    async def _on_delete(self) -> None:
        state = AppState.instance()
        if state.client is None or self._role_id is None:
            return
        self._delete_btn.setEnabled(False)
        _set_status(self._status, "deleting...", "info")
        try:
            await state.client.roles.delete(self._role_id)
            state._roles.pop(self._role_id, None)
            _set_status(self._status, "deleted", "success")
            self._role_id = None
            self.role_deleted.emit()
        except Exception as exc:
            _set_status(self._status, str(exc), "error")
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
        top_row.addWidget(_section_label("ROLES"))
        top_row.addStretch()
        self._create_status = _status_label()
        self._create_status.setFixedWidth(80)
        top_row.addWidget(self._create_status)
        self._create_btn = _action_button("[ + NEW ]", width=90)
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
        _set_status(self._create_status, "creating...", "info")
        try:
            result = await state.client.roles.create("New Role")
            state._roles[result.role_id] = result
            _set_status(self._create_status, "", "info")
            self._active_role_id = result.role_id
            self._refresh_list()
            self._edit_panel.load_role(result.role_id)
        except Exception as exc:
            _set_status(self._create_status, str(exc)[:30], "error")
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
        self._status = _status_label()
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
            _set_status(self._status, "kicked", "success")
        except Exception as exc:
            _set_status(self._status, str(exc)[:20], "error")
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
            _set_status(self._status, "banned", "success")
        except Exception as exc:
            _set_status(self._status, str(exc)[:20], "error")
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
            _tinted_icon(_ICONS_DIR / "account-cancel.svg", c.status_danger, size=16).pixmap(16, 16)
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

        self._status = _status_label()
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
            _set_status(self._status, "unbanned", "success")
        except Exception as exc:
            _set_status(self._status, str(exc)[:20], "error")
        finally:
            self._unban_btn.setEnabled(True)


class _MembersPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        c = AppState.instance().theme.colors

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
        layout.addWidget(_section_label("MEMBERS"))
        self._member_scroll, self._member_container, self._member_layout = _make_scroll_area()
        layout.addWidget(self._member_scroll, stretch=1)

        layout.addWidget(_separator())

        # Bans section
        layout.addWidget(_section_label("BANS"))
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

        layout.addWidget(_section_label("SERVER LIMITS"))

        self._scroll, self._fields_container, self._fields_layout = _make_scroll_area()
        self._fields_layout.setSpacing(4)
        layout.addWidget(self._scroll, stretch=1)

        self._fields: dict[str, QLineEdit] = {}

        layout.addSpacing(8)
        self._status = _status_label()
        layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        self._save_btn = _action_button("[ SAVE ]")
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
            _set_status(self._status, str(exc), "error")

    @asyncSlot()
    async def _on_save(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        self._save_btn.setEnabled(False)
        _set_status(self._status, "saving...", "info")
        try:
            kwargs = {}
            for key, inp in self._fields.items():
                val = inp.text().strip()
                try:
                    kwargs[key] = int(val)
                except ValueError:
                    kwargs[key] = val
            await state.client.server.update_limits(**kwargs)
            _set_status(self._status, "saved", "success")
        except Exception as exc:
            _set_status(self._status, str(exc), "error")
        finally:
            self._save_btn.setEnabled(True)


# -- Main Dialog -------------------------------------------------------------

_NAV_ITEMS = [
    ("Overview", "view-carousel.svg"),
    ("Roles", "account-group.svg"),
    ("Members", "account.svg"),
    ("Limits", "gauge.svg"),
]


class ServerSettingsDialog(QDialog):
    """Frameless server settings dialog with sidebar navigation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        c = AppState.instance().theme.colors

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(720, 520)
        self.setStyleSheet(
            f"ServerSettingsDialog {{ background-color: {c.bg_panel}; "
            f"border: 1px solid {c.border_bright}; border-radius: 6px; }}"
        )

        # Allow dragging the frameless dialog
        self._drag_pos = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -- Title bar ---------------------------------------------------------
        title_bar = QWidget()
        title_bar.setObjectName("SettingsTitleBar")
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet(
            f"#SettingsTitleBar {{ background-color: {c.bg_panel}; "
            f"border-bottom: 1px solid {c.border}; "
            f"border-top-left-radius: 6px; border-top-right-radius: 6px; }}"
        )
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 10, 0)
        title_layout.setSpacing(8)

        title_lbl = QLabel("SERVER SETTINGS")
        title_lbl.setStyleSheet(
            f"color: {c.text_primary}; font-size: 15px; font-weight: 600; "
            f"letter-spacing: 1px; border: none;"
        )
        title_layout.addWidget(title_lbl)
        title_layout.addStretch()

        close_btn = QPushButton()
        close_btn.setIcon(_tinted_icon(_ICONS_DIR / "close.svg", c.text_dim, size=18))
        close_btn.setIconSize(QSize(18, 18))
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{ border: none; border-radius: 3px; background: transparent; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        close_btn.clicked.connect(self.reject)
        title_layout.addWidget(close_btn)

        outer.addWidget(title_bar)

        # -- Body: sidebar + content -------------------------------------------
        body = QWidget()
        body.setStyleSheet("border: none;")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar nav
        nav_panel = QWidget()
        nav_panel.setFixedWidth(160)
        nav_panel.setStyleSheet(
            f"background-color: {c.bg_panel}; "
            f"border-bottom-left-radius: 6px;"
        )
        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(8, 12, 8, 12)
        nav_layout.setSpacing(2)

        self._nav_buttons: list[QPushButton] = []
        self._nav_icons: list[str] = []  # icon filenames for re-tinting
        for display_text, icon_file in _NAV_ITEMS:
            btn = QPushButton(display_text)
            btn.setIcon(_tinted_icon(_ICONS_DIR / icon_file, c.text_dim, size=14))
            btn.setIconSize(QSize(14, 14))
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ text-align: left; padding: 0 12px; font-size: 12px; "
                f"color: {c.text_dim}; border: none; border-radius: 4px; "
                f"background: transparent; }}"
                f"QPushButton:hover {{ color: {c.text_secondary}; "
                f"background-color: {c.bg_hover}; }}"
            )
            idx = len(self._nav_buttons)
            btn.clicked.connect(lambda checked, i=idx: self._on_nav_clicked(i))
            nav_layout.addWidget(btn)
            self._nav_buttons.append(btn)
            self._nav_icons.append(icon_file)

        nav_layout.addStretch()
        body_layout.addWidget(nav_panel)

        # Vertical separator
        sep = QWidget()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background-color: {c.border};")
        body_layout.addWidget(sep)

        # Content stack
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: transparent; border: none;")

        # Wrap each page in padding
        self._overview_page = _OverviewPage()
        self._roles_page = _RolesPage()
        self._members_page = _MembersPage()
        self._limits_page = _LimitsPage()

        for page in (self._overview_page, self._roles_page, self._members_page, self._limits_page):
            wrapper = QWidget()
            wrapper.setStyleSheet("background: transparent; border: none;")
            w_layout = QVBoxLayout(wrapper)
            w_layout.setContentsMargins(20, 16, 20, 16)
            w_layout.setSpacing(0)
            w_layout.addWidget(page)
            self._stack.addWidget(wrapper)

        body_layout.addWidget(self._stack, stretch=1)

        outer.addWidget(body, stretch=1)

        # Select first nav item
        self._on_nav_clicked(0)

    def _on_nav_clicked(self, index: int) -> None:
        c = AppState.instance().theme.colors
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            icon_file = self._nav_icons[i]
            if i == index:
                btn.setIcon(_tinted_icon(_ICONS_DIR / icon_file, c.text_primary, size=14))
                btn.setStyleSheet(
                    f"QPushButton {{ text-align: left; padding: 0 12px; font-size: 12px; "
                    f"color: {c.text_primary}; border: none; border-radius: 4px; "
                    f"background-color: {c.bg_active}; font-weight: 600; }}"
                )
            else:
                btn.setIcon(_tinted_icon(_ICONS_DIR / icon_file, c.text_dim, size=14))
                btn.setStyleSheet(
                    f"QPushButton {{ text-align: left; padding: 0 12px; font-size: 12px; "
                    f"color: {c.text_dim}; border: none; border-radius: 4px; "
                    f"background: transparent; }}"
                    f"QPushButton:hover {{ color: {c.text_secondary}; "
                    f"background-color: {c.bg_hover}; }}"
                )

    # -- Frameless drag support ------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 40:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001
        if self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        self._drag_pos = None
