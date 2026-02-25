"""DM sidebar – 180px panel listing direct message conversations."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from vox_client._frozen import ICONS_DIR as _ICONS_DIR
from vox_client.state import AppState
from vox_client.widgets.avatar import AvatarWidget
from vox_client.widgets.icons import tinted_icon
from vox_client.widgets.ui_helpers import clear_layout

log = logging.getLogger(__name__)


class _DMItem(QWidget):
    """Single DM conversation entry in the sidebar."""

    clicked = pyqtSignal(int)
    close_clicked = pyqtSignal(int)

    def __init__(self, dm_id: int) -> None:
        super().__init__()
        self.dm_id = dm_id
        self._active = False
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        state = AppState.instance()
        c = state.theme.colors
        self._hover_bg = c.bg_hover
        self._active_bg = c.bg_active
        self._default_style = "background-color: transparent;"
        self.setStyleSheet(self._default_style)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 6, 4)
        layout.setSpacing(8)

        # Presence dot
        partner_id = state.get_dm_partner_id(dm_id)
        presence = state.get_presence(partner_id) if partner_id else None
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

        # Avatar
        if partner_id is not None:
            layout.addWidget(AvatarWidget(partner_id, size=24, parent=self))

        # Display name
        name = state.get_dm_display_name(dm_id)
        name_color = c.text_secondary
        self._name_label = QLabel(name)
        self._name_label.setStyleSheet(f"color: {name_color}; font-size: 13px;")
        layout.addWidget(self._name_label, stretch=1)

        # Close button (hidden by default, shown on hover)
        self._close_btn = QPushButton()
        self._close_btn.setIcon(tinted_icon(_ICONS_DIR / "close.svg", c.text_dim, size=12))
        self._close_btn.setIconSize(QSize(12, 12))
        self._close_btn.setFixedSize(18, 18)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet(
            f"QPushButton {{ border: none; border-radius: 3px; background: transparent; }}"
            f"QPushButton:hover {{ background-color: {c.bg_active}; }}"
        )
        self._close_btn.clicked.connect(lambda: self.close_clicked.emit(self.dm_id))
        self._close_btn.hide()
        layout.addWidget(self._close_btn)

    def set_active(self, active: bool) -> None:
        self._active = active
        state = AppState.instance()
        c = state.theme.colors
        if active:
            self.setStyleSheet(f"background-color: {self._active_bg};")
            self._name_label.setStyleSheet(f"color: {c.accent_bright}; font-size: 13px;")
        else:
            self.setStyleSheet(self._default_style)
            self._name_label.setStyleSheet(f"color: {c.text_secondary}; font-size: 13px;")

    def enterEvent(self, event) -> None:  # noqa: ANN001
        if not self._active:
            self.setStyleSheet(f"background-color: {self._hover_bg};")
        self._close_btn.show()

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        if not self._active:
            self.setStyleSheet(self._default_style)
        self._close_btn.hide()

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        self.clicked.emit(self.dm_id)


class NewDMDialog(QDialog):
    """Simple dialog to search for a user and open a DM."""

    dm_opened = pyqtSignal(int)  # emits dm_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Direct Message")
        self.setFixedSize(320, 200)

        state = AppState.instance()
        c = state.theme.colors
        self.setStyleSheet(
            f"background-color: {c.bg_panel}; color: {c.text_primary};"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel("Find a user to message")
        header.setStyleSheet(f"color: {c.text_primary}; font-size: 13px; font-weight: 600;")
        layout.addWidget(header)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search by username...")
        self._search.setFixedHeight(30)
        self._search.setStyleSheet(
            f"background-color: {c.bg_input}; color: {c.text_primary}; "
            f"border: 1px solid {c.border}; border-radius: 4px; padding: 4px 8px;"
        )
        self._search.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search)

        # Results area
        self._results_layout = QVBoxLayout()
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(2)
        layout.addLayout(self._results_layout)

        layout.addStretch()

        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {c.text_dim}; font-size: 11px;")
        layout.addWidget(self._status)

    def _on_search_changed(self, text: str) -> None:
        clear_layout(self._results_layout)
        state = AppState.instance()
        c = state.theme.colors
        query = text.strip().lower()
        if not query:
            return

        matches = []
        for uid, member in state._members.items():
            if uid == state.user_id:
                continue
            name = state.get_display_name(uid).lower()
            username = (member.username or "").lower()
            if query in name or query in username:
                matches.append(uid)
            if len(matches) >= 5:
                break

        for uid in matches:
            name = state.get_display_name(uid)
            btn = QPushButton(f"  {name}")
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ text-align: left; background: transparent; "
                f"color: {c.text_secondary}; border: none; border-radius: 3px; font-size: 12px; }}"
                f"QPushButton:hover {{ background-color: {c.bg_hover}; color: {c.text_primary}; }}"
            )
            btn.clicked.connect(lambda checked=False, u=uid: self._open_dm(u))
            self._results_layout.addWidget(btn)

        if not matches and query:
            self._status.setText("No users found")
        else:
            self._status.setText("")

    @asyncSlot()
    async def _open_dm(self, user_id: int) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        try:
            self._status.setText("Opening DM...")
            dm = await state.client.dms.open(recipient_id=user_id)
            state._dms[dm.dm_id] = dm
            state.dm_list_changed.emit()
            self.dm_opened.emit(dm.dm_id)
            self.accept()
        except Exception:
            log.error("Failed to open DM with user %d", user_id, exc_info=True)
            self._status.setText("Failed to open DM")

    def keyPressEvent(self, event) -> None:  # noqa: ANN001
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            return  # prevent dialog close on Enter
        super().keyPressEvent(event)


class DMSidebar(QFrame):
    """180px sidebar showing DM conversations, replaces channel sidebar in DM mode."""

    dm_selected = pyqtSignal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(180)

        state = AppState.instance()
        c = state.theme.colors
        self.setStyleSheet(f"background-color: {c.bg_panel};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header row
        header_row = QWidget()
        header_row.setFixedHeight(32)
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(12, 8, 8, 4)
        header_layout.setSpacing(4)

        header_label = QLabel("DIRECT MESSAGES")
        header_label.setStyleSheet(
            f"color: {c.text_dim}; font-size: 11px; font-weight: 600; letter-spacing: 1px;"
        )
        header_layout.addWidget(header_label, stretch=1)

        add_btn = QPushButton()
        add_btn.setIcon(tinted_icon(_ICONS_DIR / "plus.svg", c.text_dim, size=14))
        add_btn.setIconSize(QSize(14, 14))
        add_btn.setFixedSize(20, 20)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            f"QPushButton {{ border: none; border-radius: 3px; background: transparent; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        add_btn.clicked.connect(self._on_new_dm)
        header_layout.addWidget(add_btn)

        outer.addWidget(header_row)

        # Scrollable DM list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none;")

        self._container = QWidget()
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._container)
        outer.addWidget(scroll)

        self._items: list[_DMItem] = []
        self._active_dm_id: int | None = None

        # Live updates
        state.dm_list_changed.connect(self.refresh)

    def restyle(self) -> None:
        c = AppState.instance().theme.colors
        self.setStyleSheet(f"background-color: {c.bg_panel};")

    def refresh(self) -> None:
        """Rebuild the DM list from cached data."""
        state = AppState.instance()

        clear_layout(self._list_layout)
        self._items.clear()

        for dm_id, dm in state._dms.items():
            if dm.is_group:
                continue  # Only show 1-on-1 DMs for now
            item = _DMItem(dm_id)
            item.clicked.connect(self._on_item_clicked)
            item.close_clicked.connect(self._on_close_dm)
            if dm_id == self._active_dm_id:
                item.set_active(True)
            self._list_layout.addWidget(item)
            self._items.append(item)

        self._list_layout.addStretch()

    def _on_item_clicked(self, dm_id: int) -> None:
        self._active_dm_id = dm_id
        for item in self._items:
            item.set_active(item.dm_id == dm_id)
        self.dm_selected.emit(dm_id)

    @asyncSlot()
    async def _on_close_dm(self, dm_id: int) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        try:
            await state.client.dms.close(dm_id)
            state._dms.pop(dm_id, None)
            if self._active_dm_id == dm_id:
                self._active_dm_id = None
            state.dm_list_changed.emit()
        except Exception:
            log.error("Failed to close DM %d", dm_id, exc_info=True)

    def _on_new_dm(self) -> None:
        dlg = NewDMDialog(self)
        dlg.dm_opened.connect(self._on_item_clicked)
        dlg.exec()

    def select_dm(self, dm_id: int) -> None:
        """Programmatically select a DM conversation."""
        self._on_item_clicked(dm_id)
