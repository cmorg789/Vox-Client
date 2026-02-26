"""Base class for frameless settings dialogs with sidebar navigation."""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt

log = logging.getLogger(__name__)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from vox_client._frozen import ICONS_DIR as _ICONS_DIR
from vox_client.state import AppState
from vox_client.widgets.icons import tinted_icon


class BaseSettingsDialog(QDialog):
    """Frameless dialog with title bar, sidebar nav, and content stack."""

    def __init__(
        self,
        title: str,
        nav_items: list[tuple[str, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        c = AppState.instance().theme.colors

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(720, 520)

        self._dialog_title = title
        self._nav_items = nav_items
        self._drag_pos = None
        self._active_nav = 0

        # Apply dialog-level style using class name
        cls_name = type(self).__name__
        self.setStyleSheet(
            f"{cls_name} {{ background-color: {c.bg_panel}; "
            f"border: 1px solid {c.border_bright}; border-radius: 6px; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -- Title bar ---------------------------------------------------------
        self._title_bar = QWidget()
        self._title_bar.setObjectName("SettingsTitleBar")
        self._title_bar.setFixedHeight(40)
        self._title_bar.setStyleSheet(
            f"#SettingsTitleBar {{ background-color: {c.bg_panel}; "
            f"border-bottom: 1px solid {c.border}; "
            f"border-top-left-radius: 6px; border-top-right-radius: 6px; }}"
        )
        title_layout = QHBoxLayout(self._title_bar)
        title_layout.setContentsMargins(16, 0, 10, 0)
        title_layout.setSpacing(8)

        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
            f"color: {c.text_primary}; font-size: 15px; font-weight: 600; "
            f"letter-spacing: 1px; border: none;"
        )
        title_layout.addWidget(self._title_lbl)
        title_layout.addStretch()

        self._close_btn = QPushButton()
        self._close_btn.setIcon(tinted_icon(_ICONS_DIR / "close.svg", c.text_dim, size=18))
        self._close_btn.setIconSize(QSize(18, 18))
        self._close_btn.setFixedSize(28, 28)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet(
            f"QPushButton {{ border: none; border-radius: 3px; background: transparent; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._close_btn.clicked.connect(self.reject)
        title_layout.addWidget(self._close_btn)

        outer.addWidget(self._title_bar)

        # -- Body: sidebar + content -------------------------------------------
        body = QWidget()
        body.setStyleSheet("border: none;")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar nav
        self._nav_panel = QWidget()
        self._nav_panel.setFixedWidth(160)
        self._nav_panel.setStyleSheet(
            f"background-color: {c.bg_panel}; "
            f"border-bottom-left-radius: 6px;"
        )
        nav_layout = QVBoxLayout(self._nav_panel)
        nav_layout.setContentsMargins(8, 12, 8, 12)
        nav_layout.setSpacing(2)

        self._nav_buttons: list[QPushButton] = []
        self._nav_icons: list[str] = []
        for display_text, icon_file in nav_items:
            btn = QPushButton(display_text)
            btn.setIcon(tinted_icon(_ICONS_DIR / icon_file, c.text_dim, size=14))
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
        body_layout.addWidget(self._nav_panel)

        # Vertical separator
        self._sep = QWidget()
        self._sep.setFixedWidth(1)
        self._sep.setStyleSheet(f"background-color: {c.border};")
        body_layout.addWidget(self._sep)

        # Content stack
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent; border: none;")

        self._build_pages()

        body_layout.addWidget(self._stack, stretch=1)

        outer.addWidget(body, stretch=1)

        # Select first nav item
        self._on_nav_clicked(0)

    def _add_page(self, page: QWidget) -> None:
        """Wrap page in standard padding and add to stack."""
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent; border: none;")
        w_layout = QVBoxLayout(wrapper)
        w_layout.setContentsMargins(20, 16, 20, 16)
        w_layout.setSpacing(0)
        w_layout.addWidget(page)
        self._stack.addWidget(wrapper)

    def _build_pages(self) -> None:
        """Subclass override: create and add pages via _add_page()."""
        raise NotImplementedError

    def _on_nav_clicked(self, index: int) -> None:
        c = AppState.instance().theme.colors
        self._active_nav = index
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            icon_file = self._nav_icons[i]
            if i == index:
                btn.setIcon(tinted_icon(_ICONS_DIR / icon_file, c.text_primary, size=14))
                btn.setStyleSheet(
                    f"QPushButton {{ text-align: left; padding: 0 12px; font-size: 12px; "
                    f"color: {c.text_primary}; border: none; border-radius: 4px; "
                    f"background-color: {c.bg_active}; font-weight: 600; }}"
                )
            else:
                btn.setIcon(tinted_icon(_ICONS_DIR / icon_file, c.text_dim, size=14))
                btn.setStyleSheet(
                    f"QPushButton {{ text-align: left; padding: 0 12px; font-size: 12px; "
                    f"color: {c.text_dim}; border: none; border-radius: 4px; "
                    f"background: transparent; }}"
                    f"QPushButton:hover {{ color: {c.text_secondary}; "
                    f"background-color: {c.bg_hover}; }}"
                )

    def _restyle(self) -> None:
        """Re-apply chrome styles after a theme change."""
        c = AppState.instance().theme.colors
        cls_name = type(self).__name__
        self.setStyleSheet(
            f"{cls_name} {{ background-color: {c.bg_panel}; "
            f"border: 1px solid {c.border_bright}; border-radius: 6px; }}"
        )
        self._title_bar.setStyleSheet(
            f"#SettingsTitleBar {{ background-color: {c.bg_panel}; "
            f"border-bottom: 1px solid {c.border}; "
            f"border-top-left-radius: 6px; border-top-right-radius: 6px; }}"
        )
        self._title_lbl.setStyleSheet(
            f"color: {c.text_primary}; font-size: 15px; font-weight: 600; "
            f"letter-spacing: 1px; border: none;"
        )
        self._close_btn.setIcon(tinted_icon(_ICONS_DIR / "close.svg", c.text_dim, size=18))
        self._close_btn.setStyleSheet(
            f"QPushButton {{ border: none; border-radius: 3px; background: transparent; }}"
            f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
        )
        self._nav_panel.setStyleSheet(
            f"background-color: {c.bg_panel}; "
            f"border-bottom-left-radius: 6px;"
        )
        self._sep.setStyleSheet(f"background-color: {c.border};")

    # -- Frameless drag support ------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 40:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001
        if self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        self._drag_pos = None
