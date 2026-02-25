"""Channel sidebar – 180px panel with server name header and categorized channels."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

from PyQt6.QtCore import QMimeData, QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)
from qasync import asyncSlot

from vox_sdk.permissions import ADMINISTRATOR, MANAGE_SERVER, MANAGE_SPACES

from vox_client._frozen import ICONS_DIR as _ICONS_DIR
from vox_client.state import AppState, _log_volume
from vox_client.widgets.avatar import AvatarWidget
from vox_client.widgets.icons import tinted_icon
from vox_client.widgets.ui_helpers import (
    close_button,
    dialog_input,
    dialog_status_label,
    small_accent_button,
)

_MIME_CATEGORY = "application/vnd.vox.category"
_MIME_CHANNEL = "application/vnd.vox.channel"


# -- Drag-and-drop helpers ---------------------------------------------------


class _DropIndicator(QWidget):
    """Thin horizontal line inserted into the layout to mark the drop position."""

    def __init__(self) -> None:
        super().__init__()
        state = AppState.instance()
        c = state.theme.colors
        self.setFixedHeight(2)
        self.setStyleSheet(f"background-color: {c.accent};")


class _DragContainerWidget(QWidget):
    """Container widget that accepts drops for category/channel reordering.

    Uses the standard PyQt layout-insertion pattern: during a drag the
    indicator widget is inserted directly into the QVBoxLayout at the
    candidate position.  On drop the indicator's layout index is read
    to determine where the item should go.  This avoids all coordinate-
    space issues between the scroll-area viewport and the content widget.
    """

    def __init__(self, sidebar: ChannelSidebar) -> None:
        super().__init__()
        self._sidebar = sidebar
        self.setAcceptDrops(True)

    # -- helpers ----------------------------------------------------------

    def _insert_indicator_at_pos(self, y: int) -> None:
        """Position the drop indicator in the layout based on viewport *y*.

        Compares *y* (viewport-relative, as delivered by drag events inside
        a QScrollArea) against each widget's midpoint mapped to the same
        coordinate space via ``mapToGlobal`` / ``mapFromGlobal``.
        """
        layout = self._sidebar._list_layout
        indicator = self._sidebar._drop_indicator
        scroll = self._sidebar._scroll
        viewport = scroll.viewport()

        # First, remove indicator from layout so it doesn't affect indices
        old_idx = layout.indexOf(indicator)
        if old_idx >= 0:
            layout.removeWidget(indicator)

        # Find insertion index among the remaining widgets
        insert_at = layout.count()
        for n in range(layout.count()):
            w = layout.itemAt(n).widget()
            if w is None:
                continue
            widget_mid_in_global = w.mapToGlobal(QPoint(0, w.height() // 2))
            widget_mid_in_viewport = viewport.mapFromGlobal(widget_mid_in_global).y()
            if y < widget_mid_in_viewport:
                insert_at = n
                break

        # Clamp to valid range and insert
        insert_at = min(insert_at, layout.count())
        layout.insertWidget(insert_at, indicator)
        indicator.show()

    # -- drag events ------------------------------------------------------

    def dragEnterEvent(self, event) -> None:  # noqa: ANN001
        mime = event.mimeData()
        if mime.hasFormat(_MIME_CATEGORY) or mime.hasFormat(_MIME_CHANNEL):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: ANN001
        mime = event.mimeData()
        y = int(event.position().y())

        if mime.hasFormat(_MIME_CATEGORY) or mime.hasFormat(_MIME_CHANNEL):
            self._insert_indicator_at_pos(y)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: ANN001
        indicator = self._sidebar._drop_indicator
        indicator.hide()
        self._sidebar._list_layout.removeWidget(indicator)

    def dropEvent(self, event) -> None:  # noqa: ANN001
        mime = event.mimeData()
        layout = self._sidebar._list_layout
        indicator = self._sidebar._drop_indicator
        drop_layout_idx = layout.indexOf(indicator)

        # Clean up indicator
        indicator.hide()
        layout.removeWidget(indicator)

        if drop_layout_idx < 0:
            return

        if mime.hasFormat(_MIME_CATEGORY):
            cat_id = int(bytes(mime.data(_MIME_CATEGORY)).decode())
            self._sidebar._handle_category_drop(cat_id, drop_layout_idx)
            event.acceptProposedAction()
        elif mime.hasFormat(_MIME_CHANNEL):
            data = bytes(mime.data(_MIME_CHANNEL)).decode()
            self._sidebar._handle_channel_drop_at(data, drop_layout_idx)
            event.acceptProposedAction()


# -- Dialogs ----------------------------------------------------------------


class _CreateSpaceDialog(QDialog):
    """Small frameless dialog for creating a feed or room in a category."""

    def __init__(self, category_id: int | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._category_id = category_id
        state = AppState.instance()
        c = state.theme.colors

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(280, 200)
        self.setStyleSheet(
            f"background-color: {c.bg_panel}; "
            f"border: 1px solid {c.border_bright}; border-radius: 6px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(0)
        title = QLabel("CREATE CHANNEL")
        title.setStyleSheet(
            f"color: {c.text_dim}; font-size: 10px; font-weight: 600; "
            f"letter-spacing: 1px; border: none;"
        )
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(close_button(self.reject))
        layout.addLayout(title_row)

        # Type combo
        self._type_combo = QComboBox()
        self._type_combo.addItem("Text Channel", "feed")
        self._type_combo.addItem("Voice Room", "room")
        self._type_combo.setStyleSheet(
            f"QComboBox {{ background-color: {c.bg_input}; color: {c.text_primary}; "
            f"border: 1px solid {c.border}; border-radius: 4px; padding: 4px 8px; "
            f"font-size: 12px; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background-color: {c.bg_panel}; "
            f"color: {c.text_primary}; selection-background-color: {c.bg_active}; "
            f"border: 1px solid {c.border}; }}"
        )
        layout.addWidget(self._type_combo)

        # Name input
        self._name_input = dialog_input("channel-name")
        self._name_input.returnPressed.connect(self._on_create)
        layout.addWidget(self._name_input)

        # Status label
        self._status = dialog_status_label()
        layout.addWidget(self._status)

        layout.addStretch()

        # Button row
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._create_btn = small_accent_button("CREATE", 80)
        self._create_btn.clicked.connect(self._on_create)
        btn_row.addWidget(self._create_btn)
        layout.addLayout(btn_row)

    @asyncSlot()
    async def _on_create(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        name = self._name_input.text().strip()
        if not name:
            c = state.theme.colors
            self._status.setText("Name required")
            self._status.setStyleSheet(f"color: {c.status_danger}; font-size: 11px; border: none;")
            return

        self._create_btn.setEnabled(False)
        c = state.theme.colors
        self._status.setText("creating...")
        self._status.setStyleSheet(f"color: {c.text_dim}; font-size: 11px; border: none;")

        try:
            ch_type = self._type_combo.currentData()
            if ch_type == "feed":
                await state.client.channels.create_feed(
                    name, category_id=self._category_id,
                )
            else:
                await state.client.channels.create_room(
                    name, category_id=self._category_id,
                )
            # Gateway event will update caches and emit layout_changed
            self.accept()
        except Exception as exc:
            log.error("Failed to create %s in category %s: %s", ch_type, self._category_id, exc)
            self._status.setText(str(exc)[:40])
            self._status.setStyleSheet(f"color: {c.status_danger}; font-size: 11px; border: none;")
            self._create_btn.setEnabled(True)


class _RenameDialog(QDialog):
    """Tiny frameless dialog for renaming a feed, room, or category."""

    def __init__(
        self,
        item_type: str,
        item_id: int,
        current_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._item_type = item_type
        self._item_id = item_id
        state = AppState.instance()
        c = state.theme.colors

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(250, 140)
        self.setStyleSheet(
            f"background-color: {c.bg_panel}; "
            f"border: 1px solid {c.border_bright}; border-radius: 6px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(0)
        title = QLabel(f"RENAME {item_type.upper()}")
        title.setStyleSheet(
            f"color: {c.text_dim}; font-size: 10px; font-weight: 600; "
            f"letter-spacing: 1px; border: none;"
        )
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(close_button(self.reject))
        layout.addLayout(title_row)

        self._name_input = dialog_input("")
        self._name_input.setText(current_name)
        self._name_input.selectAll()
        self._name_input.returnPressed.connect(self._on_save)
        layout.addWidget(self._name_input)

        self._status = dialog_status_label()
        layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._save_btn = small_accent_button("SAVE", 70)
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)
        layout.addLayout(btn_row)

    @asyncSlot()
    async def _on_save(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        name = self._name_input.text().strip()
        if not name:
            return

        self._save_btn.setEnabled(False)
        c = state.theme.colors
        self._status.setText("saving...")
        self._status.setStyleSheet(f"color: {c.text_dim}; font-size: 11px; border: none;")

        try:
            if self._item_type == "feed":
                result = await state.client.channels.update_feed(self._item_id, name=name)
                from vox_sdk.models.server import FeedInfo
                feed = FeedInfo(
                    feed_id=result.feed_id, name=result.name,
                    type=result.type, topic=result.topic,
                    category_id=result.category_id,
                )
                state._feeds[result.feed_id] = feed
                if state._layout is not None:
                    state._layout.feeds = [
                        feed if f.feed_id == result.feed_id else f
                        for f in state._layout.feeds
                    ]
            elif self._item_type == "room":
                result = await state.client.channels.update_room(self._item_id, name=name)
                from vox_sdk.models.server import RoomInfo
                room = RoomInfo(
                    room_id=result.room_id, name=result.name,
                    type=result.type, category_id=result.category_id,
                )
                state._rooms[result.room_id] = room
                if state._layout is not None:
                    state._layout.rooms = [
                        room if r.room_id == result.room_id else r
                        for r in state._layout.rooms
                    ]
            elif self._item_type == "category":
                result = await state.client.channels.update_category(self._item_id, name=name)
                from vox_sdk.models.server import CategoryInfo
                state._categories[result.category_id] = CategoryInfo(
                    category_id=result.category_id,
                    name=result.name,
                    position=result.position,
                )
                if state._layout is not None:
                    state._layout.categories = [
                        state._categories[result.category_id]
                        if ct.category_id == result.category_id else ct
                        for ct in state._layout.categories
                    ]
            state.layout_changed.emit()
            self.accept()
        except Exception as exc:
            log.error("Failed to rename %s %d: %s", self._item_type, self._item_id, exc)
            self._status.setText(str(exc)[:40])
            self._status.setStyleSheet(f"color: {c.status_danger}; font-size: 11px; border: none;")
            self._save_btn.setEnabled(True)


class _CreateCategoryDialog(QDialog):
    """Tiny frameless dialog to create a new category."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        state = AppState.instance()
        c = state.theme.colors

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(250, 140)
        self.setStyleSheet(
            f"background-color: {c.bg_panel}; "
            f"border: 1px solid {c.border_bright}; border-radius: 6px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(0)
        title = QLabel("CREATE CATEGORY")
        title.setStyleSheet(
            f"color: {c.text_dim}; font-size: 10px; font-weight: 600; "
            f"letter-spacing: 1px; border: none;"
        )
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(close_button(self.reject))
        layout.addLayout(title_row)

        self._name_input = dialog_input("Category name")
        self._name_input.returnPressed.connect(self._on_create)
        layout.addWidget(self._name_input)

        self._status = dialog_status_label()
        layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._create_btn = small_accent_button("CREATE", 80)
        self._create_btn.clicked.connect(self._on_create)
        btn_row.addWidget(self._create_btn)
        layout.addLayout(btn_row)

    @asyncSlot()
    async def _on_create(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        name = self._name_input.text().strip()
        if not name:
            c = state.theme.colors
            self._status.setText("Name required")
            self._status.setStyleSheet(f"color: {c.status_danger}; font-size: 11px; border: none;")
            return

        self._create_btn.setEnabled(False)
        c = state.theme.colors
        self._status.setText("creating...")
        self._status.setStyleSheet(f"color: {c.text_dim}; font-size: 11px; border: none;")

        try:
            await state.client.channels.create_category(name)
            # Gateway event will update caches and emit layout_changed
            self.accept()
        except Exception as exc:
            log.error("Failed to create category: %s", exc)
            self._status.setText(str(exc)[:40])
            self._status.setStyleSheet(f"color: {c.status_danger}; font-size: 11px; border: none;")
            self._create_btn.setEnabled(True)


# -- Category header ---------------------------------------------------------


class _CategoryHeader(QWidget):
    """Interactive category header: collapse arrow + name + "+" button."""

    create_requested = pyqtSignal(int)  # category_id

    def __init__(
        self,
        category_id: int,
        name: str,
        can_manage: bool,
        sidebar: ChannelSidebar,
    ) -> None:
        super().__init__()
        self.category_id = category_id
        self._name = name
        self._can_manage = can_manage
        self._sidebar = sidebar
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(28)

        state = AppState.instance()
        c = state.theme.colors

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 4, 12, 4)
        row.setSpacing(2)

        # Collapse arrow
        self._arrow = QLabel("\u25b8")
        self._arrow.setFixedWidth(12)
        self._arrow.setStyleSheet(
            f"color: {c.text_dim}; font-size: 9px; border: none;"
        )
        row.addWidget(self._arrow)

        # Category name
        self._label = QLabel(name.upper())
        self._label.setStyleSheet(
            f"color: {c.text_dim}; font-size: 10px; font-weight: 600; "
            f"letter-spacing: 1px; border: none;"
        )
        row.addWidget(self._label, stretch=1)

        # "+" button (only if user can manage)
        if can_manage:
            self._plus_btn = QPushButton()
            self._plus_btn.setIcon(tinted_icon(_ICONS_DIR / "plus.svg", c.text_dim, size=14))
            self._plus_btn.setIconSize(QSize(14, 14))
            self._plus_btn.setFixedSize(18, 18)
            self._plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._plus_btn.setStyleSheet("border: none; background: transparent;")
            self._plus_btn.clicked.connect(self._on_plus_clicked)
            row.addWidget(self._plus_btn)

        self._drag_start_pos: QPoint | None = None
        self._drag_started = False
        self._update_arrow()

    @property
    def collapsed(self) -> bool:
        return self.category_id in self._sidebar._collapsed_categories

    def _update_arrow(self) -> None:
        self._arrow.setText("\u25b8" if self.collapsed else "\u25be")

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_started = False
            if self._can_manage:
                self._drag_start_pos = event.pos()
            else:
                self._drag_start_pos = None

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001
        if (
            self._drag_start_pos is not None
            and not self._drag_started
            and (event.pos() - self._drag_start_pos).manhattanLength()
            > QApplication.startDragDistance()
        ):
            self._drag_started = True
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(_MIME_CATEGORY, str(self.category_id).encode())
            drag.setMimeData(mime)
            # Semi-transparent pixmap of the header
            pixmap = self.grab()
            pixmap.setDevicePixelRatio(self.devicePixelRatioF())
            drag.setPixmap(pixmap)
            drag.setHotSpot(event.pos())
            drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton and not self._drag_started:
            # Toggle collapse (original click behavior)
            if self.collapsed:
                self._sidebar._collapsed_categories.discard(self.category_id)
            else:
                self._sidebar._collapsed_categories.add(self.category_id)
            self._sidebar.populate()
        self._drag_start_pos = None
        self._drag_started = False

    def _on_plus_clicked(self) -> None:
        dlg = _CreateSpaceDialog(self.category_id, parent=self.window())
        dlg.exec()

    def contextMenuEvent(self, event) -> None:  # noqa: ANN001
        if not self._can_manage:
            return
        state = AppState.instance()
        c = state.theme.colors

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background-color: {c.bg_panel}; color: {c.text_primary}; "
            f"border: 1px solid {c.border_bright}; border-radius: 4px; padding: 4px; "
            f"font-size: 12px; }}"
            f"QMenu::item {{ padding: 6px 12px; border-radius: 3px; }}"
            f"QMenu::item:selected {{ background-color: {c.bg_active}; }}"
            f"QMenu::separator {{ height: 1px; background: {c.border}; margin: 4px 8px; }}"
        )

        create_act = menu.addAction("Create Channel")
        rename_act = menu.addAction("Rename Category")
        menu.addSeparator()
        delete_act = menu.addAction("Delete Category")
        delete_act.setIcon(tinted_icon(_ICONS_DIR / "close.svg", c.status_danger, size=14))

        action = menu.exec(event.globalPos())
        if action is None:
            return
        if action is create_act:
            self._on_plus_clicked()
        elif action is rename_act:
            dlg = _RenameDialog("category", self.category_id, self._name, parent=self.window())
            dlg.exec()
        elif action is delete_act:
            self._delete_category()

    @asyncSlot()
    async def _delete_category(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        try:
            await state.client.channels.delete_category(self.category_id)
            state._categories.pop(self.category_id, None)
            if state._layout is not None:
                state._layout.categories = [
                    ct for ct in state._layout.categories
                    if ct.category_id != self.category_id
                ]
            state.layout_changed.emit()
        except Exception:
            log.error("Failed to delete category %d", self.category_id, exc_info=True)


# -- Channel item ------------------------------------------------------------


class _ChannelItem(QWidget):
    """Single clickable channel entry."""

    clicked = pyqtSignal(int, str)  # (id, item_type)

    def __init__(
        self,
        feed_id: int,
        name: str,
        is_voice: bool = False,
        item_type: str = "feed",
        can_manage: bool = False,
    ) -> None:
        super().__init__()
        self.feed_id = feed_id
        self._active = False
        self._is_voice = is_voice
        self._name = name
        self.item_type = item_type
        self._can_manage = can_manage
        self._drag_start_pos: QPoint | None = None
        self._drag_started = False
        self._icon_svg = "volume-high.svg" if is_voice else "pound.svg"

        self._bg_color: str | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(6)

        self._prefix_icon = QLabel()
        self._prefix_icon.setFixedSize(16, 16)
        self._prefix_icon.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout.addWidget(self._prefix_icon)

        self._name_label = QLabel(name)
        self._name_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout.addWidget(self._name_label, stretch=1)

        self._update_style()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update_style()

    def _set_prefix_icon(self, color: str) -> None:
        self._prefix_icon.setPixmap(
            tinted_icon(_ICONS_DIR / self._icon_svg, color, size=16).pixmap(QSize(16, 16))
        )

    def paintEvent(self, event) -> None:  # noqa: ANN001
        if self._bg_color:
            from PyQt6.QtGui import QPainter, QColor
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._bg_color))
            painter.drawRoundedRect(self.rect(), 4, 4)
            painter.end()

    def _update_style(self) -> None:
        state = AppState.instance()
        c = state.theme.colors
        if self._active:
            self._bg_color = c.bg_active
            self._name_label.setStyleSheet(
                f"color: {c.accent_bright}; font-size: 13px; font-weight: 600;"
            )
            self._set_prefix_icon(c.text_dim)
        else:
            self._bg_color = None
            self._name_label.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 13px;"
            )
            self._set_prefix_icon(c.text_dim)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_started = False
            if self._can_manage:
                self._drag_start_pos = event.pos()
            else:
                self._drag_start_pos = None

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001
        if (
            self._drag_start_pos is not None
            and not self._drag_started
            and (event.pos() - self._drag_start_pos).manhattanLength()
            > QApplication.startDragDistance()
        ):
            self._drag_started = True
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(
                _MIME_CHANNEL,
                f"{self.item_type}:{self.feed_id}".encode(),
            )
            drag.setMimeData(mime)
            pixmap = self.grab()
            pixmap.setDevicePixelRatio(self.devicePixelRatioF())
            drag.setPixmap(pixmap)
            drag.setHotSpot(event.pos())
            drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton and not self._drag_started:
            self.clicked.emit(self.feed_id, self.item_type)
        self._drag_start_pos = None
        self._drag_started = False

    def enterEvent(self, event) -> None:  # noqa: ANN001
        if not self._active:
            state = AppState.instance()
            c = state.theme.colors
            self._bg_color = c.bg_hover
            self.update()
            self._name_label.setStyleSheet(
                f"color: {c.text_primary}; font-size: 13px;"
            )
            self._set_prefix_icon(c.text_dim)

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        if not self._active:
            self._update_style()

    def contextMenuEvent(self, event) -> None:  # noqa: ANN001
        if not self._can_manage:
            return
        state = AppState.instance()
        c = state.theme.colors

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background-color: {c.bg_panel}; color: {c.text_primary}; "
            f"border: 1px solid {c.border_bright}; border-radius: 4px; padding: 4px; "
            f"font-size: 12px; }}"
            f"QMenu::item {{ padding: 6px 12px; border-radius: 3px; }}"
            f"QMenu::item:selected {{ background-color: {c.bg_active}; }}"
            f"QMenu::separator {{ height: 1px; background: {c.border}; margin: 4px 8px; }}"
        )

        rename_act = menu.addAction("Rename")
        settings_act = menu.addAction("Settings")
        settings_act.setIcon(tinted_icon(_ICONS_DIR / "cog.svg", c.text_secondary, size=14))
        menu.addSeparator()
        delete_act = menu.addAction("Delete")
        delete_act.setIcon(tinted_icon(_ICONS_DIR / "close.svg", c.status_danger, size=14))

        action = menu.exec(event.globalPos())
        if action is None:
            return
        if action is rename_act:
            dlg = _RenameDialog(self.item_type, self.feed_id, self._name, parent=self.window())
            dlg.exec()
        elif action is settings_act:
            from vox_client.widgets.channel_settings import ChannelSettingsDialog
            dlg = ChannelSettingsDialog(self.item_type, self.feed_id, parent=self.window())
            dlg.exec()
        elif action is delete_act:
            self._delete_channel()

    @asyncSlot()
    async def _delete_channel(self) -> None:
        state = AppState.instance()
        if state.client is None:
            return
        try:
            if self.item_type == "feed":
                await state.client.channels.delete_feed(self.feed_id)
                state._feeds.pop(self.feed_id, None)
                if state._layout is not None:
                    state._layout.feeds = [
                        f for f in state._layout.feeds if f.feed_id != self.feed_id
                    ]
            else:
                await state.client.channels.delete_room(self.feed_id)
                state._rooms.pop(self.feed_id, None)
                if state._layout is not None:
                    state._layout.rooms = [
                        r for r in state._layout.rooms if r.room_id != self.feed_id
                    ]
            state.layout_changed.emit()
        except Exception:
            log.error("Failed to delete %s %d", self.item_type, self.feed_id, exc_info=True)



# -- Main sidebar widget -----------------------------------------------------


class _VoiceMemberEntry(QWidget):
    """Non-interactive row showing a voice participant under a room entry."""

    def __init__(self, user_id: int) -> None:
        super().__init__()
        self.user_id = user_id
        self.setFixedHeight(22)
        state = AppState.instance()
        c = state.theme.colors

        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 1, 8, 1)
        layout.setSpacing(4)

        # Avatar circle (async-loads image if available)
        self._avatar = AvatarWidget(user_id, size=16, parent=self)
        self._avatar.set_speaking(state.is_speaking(user_id))
        layout.addWidget(self._avatar)

        # Listen for speaking state changes
        state.speaking_changed.connect(self._on_speaking_changed)

        name = state.get_display_name(user_id)
        name_label = QLabel(name)
        name_label.setStyleSheet(f"color: {c.text_dim}; font-size: 11px;")
        layout.addWidget(name_label, stretch=1)

        # Mute/deafen indicators
        vm = None
        for rid, members in state._voice_room_members.items():
            if user_id in members:
                vm = members[user_id]
                break

        if vm and vm.deaf:
            deaf_icon = QLabel()
            deaf_icon.setPixmap(
                tinted_icon(_ICONS_DIR / "headphones-off.svg", c.text_dim, size=10).pixmap(QSize(10, 10))
            )
            deaf_icon.setFixedSize(10, 10)
            layout.addWidget(deaf_icon)
        elif vm and vm.mute:
            mute_icon = QLabel()
            mute_icon.setPixmap(
                tinted_icon(_ICONS_DIR / "microphone-off.svg", c.text_dim, size=10).pixmap(QSize(10, 10))
            )
            mute_icon.setFixedSize(10, 10)
            layout.addWidget(mute_icon)

    def _on_speaking_changed(self, user_id: int, speaking: bool) -> None:
        if user_id == self.user_id:
            self._avatar.set_speaking(speaking)

    def contextMenuEvent(self, event) -> None:  # noqa: ANN001
        state = AppState.instance()
        if self.user_id == state.user_id:
            return  # no self-volume control

        c = state.theme.colors
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background-color: {c.bg_panel}; color: {c.text_primary}; "
            f"border: 1px solid {c.border_bright}; border-radius: 4px; padding: 4px; "
            f"font-size: 12px; }}"
            f"QMenu::item {{ padding: 6px 12px; border-radius: 3px; }}"
            f"QMenu::item:selected {{ background-color: {c.bg_active}; }}"
        )

        slider_widget = QWidget()
        slider_widget.setStyleSheet("background: transparent; border: none;")
        sl = QHBoxLayout(slider_widget)
        sl.setContentsMargins(8, 4, 8, 4)
        sl.setSpacing(6)

        label = QLabel("Volume")
        label.setStyleSheet(f"color: {c.text_secondary}; font-size: 11px; border: none;")
        sl.addWidget(label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 200)
        current = int(state.voice_get_user_volume(self.user_id) * 100)
        slider.setValue(current)
        sl.addWidget(slider, stretch=1)

        pct_label = QLabel(f"{current}%")
        pct_label.setFixedWidth(32)
        pct_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pct_label.setStyleSheet(f"color: {c.text_dim}; font-size: 11px; border: none;")
        sl.addWidget(pct_label)

        uid = self.user_id

        def on_change(val: int) -> None:
            pct_label.setText(f"{val}%")
            state.voice_set_user_volume(uid, _log_volume(val))

        slider.valueChanged.connect(on_change)

        action = QWidgetAction(menu)
        action.setDefaultWidget(slider_widget)
        menu.addAction(action)
        menu.exec(event.globalPos())



class ChannelSidebar(QWidget):
    """Categorized channel list with server name header."""

    feed_selected = pyqtSignal(int)
    room_selected = pyqtSignal(int)
    settings_clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(180)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        state = AppState.instance()
        c = state.theme.colors

        self.setObjectName("ChannelSidebar")
        self.setStyleSheet(f"#ChannelSidebar {{ background-color: {c.bg_panel}; }}")

        # Server name header row
        self._header_widget = QFrame()
        self._header_widget.setObjectName("ChannelHeader")
        self._header_widget.setFixedHeight(40)
        self._header_widget.setStyleSheet(
            f"#ChannelHeader {{ background-color: {c.bg_panel}; "
            f"border-bottom: 1px solid {c.border}; }}"
        )
        header_row = QHBoxLayout(self._header_widget)
        header_row.setContentsMargins(12, 0, 4, 0)
        header_row.setSpacing(2)

        self._header = QLabel()
        self._header.setStyleSheet(
            f"color: {c.text_primary}; font-weight: 600; font-size: 13px;"
        )
        header_row.addWidget(self._header, stretch=1)

        # "+" button for creating categories (permission-gated, populated in populate())
        self._add_category_btn = QPushButton()
        self._add_category_btn.setIcon(tinted_icon(_ICONS_DIR / "plus.svg", c.text_dim, size=16))
        self._add_category_btn.setIconSize(QSize(16, 16))
        self._add_category_btn.setFixedSize(24, 24)
        self._add_category_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_category_btn.setStyleSheet(
            "border: none; padding: 0px; background: transparent;"
        )
        self._add_category_btn.clicked.connect(self._on_add_category)
        self._add_category_btn.hide()
        header_row.addWidget(self._add_category_btn)

        self._settings_btn = QPushButton()
        self._settings_btn.setIcon(tinted_icon(_ICONS_DIR / "cog.svg", c.text_dim))
        self._settings_btn.setIconSize(QSize(16, 16))
        self._settings_btn.setFixedSize(24, 24)
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setStyleSheet(
            "border: none; padding: 0px; background: transparent;"
        )
        self._settings_btn.clicked.connect(self.settings_clicked)
        self._settings_btn.hide()
        header_row.addWidget(self._settings_btn)

        outer.addWidget(self._header_widget)

        # Scrollable channel list
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"border: none; background-color: {c.bg_panel};")

        self._container = _DragContainerWidget(self)
        self._container.setStyleSheet(f"background-color: {c.bg_panel};")
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(4, 8, 4, 8)
        self._list_layout.setSpacing(1)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll, stretch=1)

        self._drop_indicator = _DropIndicator()

        self._items: list[_ChannelItem] = []
        self._headers: list[_CategoryHeader] = []
        self._voice_entries: list[_VoiceMemberEntry] = []
        self._active_feed_id: int | None = None
        self._active_item_type: str | None = None
        self._collapsed_categories: set[int] = set()

    def restyle(self) -> None:
        """Re-apply container-level inline styles after a theme change."""
        c = AppState.instance().theme.colors
        self.setStyleSheet(f"#ChannelSidebar {{ background-color: {c.bg_panel}; }}")
        self._header_widget.setStyleSheet(
            f"#ChannelHeader {{ background-color: {c.bg_panel}; "
            f"border-bottom: 1px solid {c.border}; }}"
        )
        self._header.setStyleSheet(
            f"color: {c.text_primary}; font-weight: 600; font-size: 13px;"
        )
        self._add_category_btn.setIcon(tinted_icon(_ICONS_DIR / "plus.svg", c.text_dim, size=14))
        self._settings_btn.setIcon(tinted_icon(_ICONS_DIR / "cog.svg", c.text_dim))
        self._scroll.setStyleSheet(f"border: none; background-color: {c.bg_panel};")
        self._container.setStyleSheet(f"background-color: {c.bg_panel};")

    def _on_add_category(self) -> None:
        dlg = _CreateCategoryDialog(parent=self.window())
        dlg.exec()

    def populate(self) -> None:
        """Build channel list from cached layout data."""
        state = AppState.instance()
        c = state.theme.colors
        layout = state._layout
        if layout is None:
            return

        # Compute permissions once
        can_manage = (
            state.user_has_permission(MANAGE_SPACES)
            or state.user_has_permission(ADMINISTRATOR)
        )

        # Update header
        arrow = "\u25b8"
        self._header.setText(f"{arrow}  {state.server_name}")

        # Show cog if user can manage server
        if state.user_has_permission(MANAGE_SERVER) or state.user_has_permission(ADMINISTRATOR):
            self._settings_btn.show()
        else:
            self._settings_btn.hide()

        # Show "+" category button if user can manage spaces
        if can_manage:
            self._add_category_btn.show()
        else:
            self._add_category_btn.hide()

        # Clear existing items
        for item in self._items:
            item.deleteLater()
        self._items.clear()
        for hdr in self._headers:
            hdr.deleteLater()
        self._headers.clear()
        for ve in self._voice_entries:
            ve.deleteLater()
        self._voice_entries.clear()
        # Clear any remaining widgets
        while self._list_layout.count():
            child = self._list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Group channels (feeds + rooms merged) by category, sorted by position
        cat_channels: dict[int | None, list] = {}

        for feed in layout.feeds:
            cat_channels.setdefault(feed.category_id, []).append(
                ("feed", feed.feed_id, feed.name, feed.position, False)
            )
        for room in layout.rooms:
            cat_channels.setdefault(room.category_id, []).append(
                ("room", room.room_id, room.name, room.position, True)
            )
        # Sort each category's channels by position, then name as tiebreaker
        for channels in cat_channels.values():
            channels.sort(key=lambda c: (c[3], c[2]))

        cats = sorted(layout.categories, key=lambda ct: ct.position)

        for cat in cats:
            # Category header
            header = _CategoryHeader(cat.category_id, cat.name, can_manage, self)
            self._list_layout.addWidget(header)
            self._headers.append(header)

            # Skip children if collapsed
            if cat.category_id in self._collapsed_categories:
                continue

            for item_type, item_id, name, _pos, is_voice in cat_channels.get(cat.category_id, []):
                item = _ChannelItem(
                    item_id, name, is_voice=is_voice,
                    item_type=item_type, can_manage=can_manage,
                )
                # Highlight connected room
                if item_type == "room" and item_id == state.voice_room_id:
                    item._set_prefix_icon(c.status_success)
                item.clicked.connect(self._on_channel_clicked)
                self._list_layout.addWidget(item)
                self._items.append(item)
                # Voice member entries under rooms
                if item_type == "room":
                    for uid in state.get_voice_members(item_id):
                        entry = _VoiceMemberEntry(uid)
                        self._list_layout.addWidget(entry)
                        self._voice_entries.append(entry)

        # Uncategorized
        uncategorized = cat_channels.get(None, [])
        if uncategorized:
            for item_type, item_id, name, _pos, is_voice in uncategorized:
                item = _ChannelItem(
                    item_id, name, is_voice=is_voice,
                    item_type=item_type, can_manage=can_manage,
                )
                if item_type == "room" and item_id == state.voice_room_id:
                    item._set_prefix_icon(c.status_success)
                item.clicked.connect(self._on_channel_clicked)
                self._list_layout.addWidget(item)
                self._items.append(item)
                if item_type == "room":
                    for uid in state.get_voice_members(item_id):
                        entry = _VoiceMemberEntry(uid)
                        self._list_layout.addWidget(entry)
                        self._voice_entries.append(entry)

        self._list_layout.addStretch()

        # Restore active selection
        if self._active_feed_id is not None:
            for item in self._items:
                item.set_active(
                    item.feed_id == self._active_feed_id
                    and item.item_type == self._active_item_type
                )

    def _on_channel_clicked(self, item_id: int, item_type: str) -> None:
        if item_type == "room":
            # Don't change the active feed highlight for voice rooms
            self.room_selected.emit(item_id)
            return
        self._active_feed_id = item_id
        self._active_item_type = item_type
        for item in self._items:
            item.set_active(
                item.feed_id == item_id and item.item_type == item_type
            )
        self.feed_selected.emit(item_id)

    # -- Drop handling -------------------------------------------------------

    def _walk_layout_widgets(self) -> list[QWidget]:
        """Return all non-indicator widgets in layout order."""
        result = []
        for i in range(self._list_layout.count()):
            w = self._list_layout.itemAt(i).widget()
            if w is not None and w is not self._drop_indicator:
                result.append(w)
        return result

    @asyncSlot()
    async def _handle_category_drop(self, category_id: int, drop_layout_idx: int) -> None:
        """Reorder a category based on where the indicator was in the layout."""
        state = AppState.instance()
        if state.client is None or state._layout is None:
            return

        # Walk the layout widgets (without the indicator) to determine
        # which category-header index the drop corresponds to.
        widgets = self._walk_layout_widgets()
        header_index = 0
        for i, w in enumerate(widgets):
            if i >= drop_layout_idx:
                break
            if isinstance(w, _CategoryHeader):
                header_index += 1

        # header_index is now "insert before this header ordinal"
        cats = sorted(state._layout.categories, key=lambda ct: ct.position)
        if header_index <= 0:
            new_pos = cats[0].position - 1 if cats else 0
        elif header_index >= len(cats):
            new_pos = cats[-1].position + 1 if cats else 0
        else:
            new_pos = header_index

        try:
            await state.client.channels.update_category(
                category_id, position=new_pos,
            )
            await state.refresh_layout()
        except Exception:
            log.error("Failed to reorder category %d", category_id, exc_info=True)

    def _handle_channel_drop_at(self, data: str, drop_layout_idx: int) -> None:
        """Determine target category and position from the indicator's layout index."""
        item_type, item_id_str = data.split(":", 1)
        item_id = int(item_id_str)

        widgets = self._walk_layout_widgets()

        # Find the nearest category header BEFORE the drop index
        current_cat_id: int | None = None
        channel_pos = 0
        for i, w in enumerate(widgets):
            if i >= drop_layout_idx:
                break
            if isinstance(w, _CategoryHeader):
                current_cat_id = w.category_id
                channel_pos = 0
            elif isinstance(w, _ChannelItem):
                # Don't count the dragged item itself
                if w.feed_id == item_id and w.item_type == item_type:
                    continue
                channel_pos += 1

        self._handle_channel_drop(item_type, item_id, current_cat_id, channel_pos)

    @asyncSlot()
    async def _handle_channel_drop(
        self,
        item_type: str,
        item_id: int,
        target_category_id: int | None,
        position: int,
    ) -> None:
        """Move a channel to a new category/position via SDK."""
        state = AppState.instance()
        if state.client is None:
            return

        try:
            if item_type == "feed":
                await state.client.channels.update_feed(
                    item_id, category_id=target_category_id, position=position,
                )
            else:
                await state.client.channels.update_room(
                    item_id, category_id=target_category_id, position=position,
                )
            # Refetch the full layout so ALL items' positions are up-to-date
            await state.refresh_layout()
        except Exception:
            log.error("Failed to reorder %s %d", item_type, item_id, exc_info=True)
