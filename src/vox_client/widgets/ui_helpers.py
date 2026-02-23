"""Shared UI factory functions and utilities used across multiple widgets."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

from vox_client._frozen import ICONS_DIR as _ICONS_DIR
from vox_client.state import AppState
from vox_client.widgets.icons import tinted_icon


# -- Labels ------------------------------------------------------------------

def section_label(text: str, *, top_pad: int = 4) -> QLabel:
    """Section header label (10px, bold, dimmed, uppercase with letter-spacing)."""
    c = AppState.instance().theme.colors
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {c.text_dim}; font-size: 10px; font-weight: 600; "
        f"letter-spacing: 1px; padding: {top_pad}px 0 6px 0; border: none;"
    )
    return lbl


def field_label(text: str) -> QLabel:
    """Uppercase field label (11px, bold, dimmed)."""
    c = AppState.instance().theme.colors
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color: {c.text_dim}; font-size: 11px; font-weight: 600; "
        f"letter-spacing: 0.5px; padding: 2px 0 0px 0; border: none;"
    )
    return lbl


# -- Buttons -----------------------------------------------------------------

def action_button(text: str, width: int = 110) -> QPushButton:
    """Accent-colored primary action button."""
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


def danger_button(text: str, width: int = 110) -> QPushButton:
    """Red danger button."""
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


def small_accent_button(text: str, width: int, height: int = 28) -> QPushButton:
    """Compact accent button used in small dialogs."""
    c = AppState.instance().theme.colors
    btn = QPushButton(text)
    btn.setFixedHeight(height)
    btn.setFixedWidth(width)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(
        f"QPushButton {{ background-color: {c.accent_dim}; border: 1px solid {c.accent}; "
        f"color: {c.accent_bright}; border-radius: 4px; font-size: 11px; font-weight: 600; }}"
        f"QPushButton:hover {{ background-color: {c.accent}; border-color: {c.accent_bright}; color: {c.text_on_accent}; }}"
        f"QPushButton:disabled {{ background-color: {c.bg_active}; color: {c.text_dim}; border-color: {c.border}; }}"
    )
    return btn


def close_button(on_click: callable) -> QPushButton:
    """Standard 28x28 close icon button (mdi-close, 18px icon, 3px radius)."""
    c = AppState.instance().theme.colors
    btn = QPushButton()
    btn.setIcon(tinted_icon(_ICONS_DIR / "close.svg", c.text_dim, size=18))
    btn.setIconSize(QSize(18, 18))
    btn.setFixedSize(28, 28)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(
        f"QPushButton {{ border: none; border-radius: 3px; background: transparent; }}"
        f"QPushButton:hover {{ background-color: {c.bg_hover}; }}"
    )
    btn.clicked.connect(on_click)
    return btn


# -- Separators & status -----------------------------------------------------

def separator() -> QFrame:
    """Horizontal line divider."""
    c = AppState.instance().theme.colors
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet(f"background-color: {c.border}; border: none;")
    return line


def status_label() -> QLabel:
    """Empty 18px-high label for inline status messages."""
    lbl = QLabel("")
    lbl.setFixedHeight(18)
    lbl.setStyleSheet("border: none; padding: 0;")
    return lbl


def set_status(label: QLabel, text: str, kind: str = "info") -> None:
    """Set status text and color on a label."""
    c = AppState.instance().theme.colors
    color_map = {
        "info": c.text_dim,
        "error": c.status_danger,
        "success": c.status_success,
        "warning": c.status_warning,
    }
    color = color_map.get(kind, c.text_dim)
    label.setText(text)
    label.setStyleSheet(f"color: {color}; border: none; padding: 0; font-size: 11px;")


# -- Dialog helpers ----------------------------------------------------------

def dialog_input(placeholder: str, *, height: int = 28) -> QLineEdit:
    """Themed QLineEdit for use in small dialogs."""
    c = AppState.instance().theme.colors
    inp = QLineEdit()
    inp.setPlaceholderText(placeholder)
    inp.setFixedHeight(height)
    inp.setStyleSheet(
        f"background-color: {c.bg_input}; color: {c.text_primary}; "
        f"border: 1px solid {c.border}; border-radius: 4px; "
        f"padding: 4px 8px; font-size: 12px;"
    )
    return inp


def dialog_status_label() -> QLabel:
    """16px-high inline status label for small dialogs."""
    c = AppState.instance().theme.colors
    lbl = QLabel("")
    lbl.setFixedHeight(16)
    lbl.setStyleSheet(f"color: {c.text_dim}; font-size: 11px; border: none;")
    return lbl


# -- Layout utilities --------------------------------------------------------

def clear_layout(layout: QLayout) -> None:
    """Remove and delete all widgets from a layout."""
    while layout.count():
        child = layout.takeAt(0)
        if child.widget():
            child.widget().deleteLater()


async def await_dialog(dlg: QDialog) -> None:
    """Show a modal dialog and await its completion (async-friendly)."""
    dlg.setModal(True)
    dlg.show()
    future: asyncio.Future[None] = asyncio.get_event_loop().create_future()
    dlg.finished.connect(lambda _result: future.set_result(None))
    await future
