"""Catppuccin-based theming system for Vox Client."""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

from catppuccin import PALETTE
from PySide6.QtCore import QSettings


def _blend_hex(fg: str, bg: str, alpha: float) -> str:
    """Blend *fg* over *bg* at the given *alpha* (0-1). Returns #RRGGBB."""
    fr, fg_g, fb = int(fg[1:3], 16), int(fg[3:5], 16), int(fg[5:7], 16)
    br, bg_g, bb = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
    r = int(fr * alpha + br * (1 - alpha))
    g = int(fg_g * alpha + bg_g * (1 - alpha))
    b = int(fb * alpha + bb * (1 - alpha))
    return f"#{r:02x}{g:02x}{b:02x}"


@dataclass(frozen=True)
class ThemeColors:
    """All semantic color tokens for the UI."""

    # Backgrounds
    bg_deep: str
    bg_main: str
    bg_panel: str
    bg_input: str
    bg_hover: str
    bg_active: str

    # Borders
    border: str
    border_bright: str

    # Text
    text_primary: str
    text_secondary: str
    text_dim: str

    # Accent
    accent: str
    accent_dim: str
    accent_bright: str

    # Role colors
    role_admin: str
    role_mod: str
    role_dev: str
    role_member: str

    # Status / semantic
    status_success: str
    status_danger: str
    status_danger_dim: str
    status_warning: str
    status_idle: str
    status_offline: str

    # Computed
    text_on_accent: str
    mention_bg: str


class Theme:
    """Generates a full set of theme colors and QSS from a Catppuccin flavor."""

    def __init__(self, flavor: str = "mocha") -> None:
        self.flavor = flavor
        self.colors = self._compute_colors(flavor)

    @staticmethod
    def _compute_colors(flavor: str) -> ThemeColors:
        f = getattr(PALETTE, flavor)
        c = f.colors

        crust = c.crust.hex
        base = c.base.hex
        mantle = c.mantle.hex
        flamingo = c.flamingo.hex

        return ThemeColors(
            # Backgrounds
            bg_deep=crust,
            bg_main=base,
            bg_panel=mantle,
            bg_input=crust,
            bg_hover=c.surface0.hex,
            bg_active=c.surface1.hex,
            # Borders
            border=c.surface0.hex,
            border_bright=c.surface1.hex,
            # Text
            text_primary=c.text.hex,
            text_secondary=c.subtext0.hex,
            text_dim=c.overlay0.hex,
            # Accent
            accent=c.mauve.hex,
            accent_dim=c.surface2.hex,
            accent_bright=c.lavender.hex,
            # Role colors
            role_admin=c.red.hex,
            role_mod=c.peach.hex,
            role_dev=c.blue.hex,
            role_member=c.subtext1.hex,
            # Status / semantic
            status_success=c.green.hex,
            status_danger=c.red.hex,
            status_danger_dim=_blend_hex(flamingo, crust, 0.20),
            status_warning=c.yellow.hex,
            status_idle=c.overlay1.hex,
            status_offline=c.surface2.hex,
            # Computed
            text_on_accent=c.text.hex if flavor == "latte" else "#ffffff",
            mention_bg=_blend_hex(c.mauve.hex, base, 0.15),
        )

    def set_flavor(self, flavor: str) -> None:
        self.flavor = flavor
        self.colors = self._compute_colors(flavor)

    # -- QSS generation ------------------------------------------------------

    def generate_qss(self) -> str:
        c = self.colors
        return f"""
/* Vox Theme – {self.flavor} */

* {{
    font-family: "JetBrains Mono";
    font-size: 13px;
}}

QWidget {{
    background-color: {c.bg_deep};
    color: {c.text_secondary};
}}

QMainWindow {{
    background-color: {c.bg_deep};
}}

/* ---------- Input fields ---------- */

QLineEdit, QTextEdit {{
    background-color: {c.bg_input};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 8px 4px;
    selection-background-color: {c.accent_dim};
    selection-color: {c.text_primary};
}}

QLineEdit:focus, QTextEdit:focus {{
    border-color: {c.accent};
}}

/* ---------- Buttons ---------- */

QPushButton {{
    background-color: transparent;
    color: {c.text_secondary};
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 6px 16px;
    font-size: 12px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {c.bg_hover};
    color: {c.text_primary};
    border-color: {c.border_bright};
}}

QPushButton:pressed {{
    background-color: {c.bg_active};
    color: {c.text_primary};
}}

QPushButton:disabled {{
    color: {c.text_dim};
    border-color: {c.border};
}}

QPushButton[flat="true"] {{
    border: none;
    color: {c.text_dim};
    padding: 2px 0px;
}}

QPushButton[flat="true"]:hover {{
    color: {c.accent_bright};
    background-color: transparent;
}}

/* ---------- Lists ---------- */

QListWidget {{
    background-color: transparent;
    border: none;
    outline: none;
    padding: 0px;
}}

QListWidget::item {{
    padding: 3px 8px;
    border: none;
    color: {c.text_secondary};
}}

QListWidget::item:selected {{
    background-color: {c.bg_active};
    color: {c.text_primary};
}}

QListWidget::item:hover {{
    background-color: {c.bg_hover};
    color: {c.text_secondary};
}}

/* ---------- Scroll areas ---------- */

QScrollArea {{
    border: none;
    background-color: transparent;
}}

QScrollBar:vertical {{
    background-color: {c.bg_hover};
    width: 6px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background-color: {c.accent_dim};
    min-height: 20px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {c.accent_dim};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    height: 0px;
}}

/* ---------- Labels ---------- */

QLabel {{
    background: transparent;
}}

/* ---------- Splitter ---------- */

QSplitter::handle {{
    background-color: {c.border};
    width: 1px;
}}

/* ---------- Slider ---------- */

QSlider::groove:horizontal {{
    border: none;
    height: 4px;
    background: {c.bg_input};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {c.accent_bright};
    border: 2px solid {c.bg_deep};
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}}

QSlider::handle:horizontal:hover {{
    background: {c.accent_bright};
}}
"""


def role_color_for_int(color_int: int | None) -> str | None:
    """Convert an SDK role color integer to a hex string.

    Role colors are stored as 24-bit RGB integers (e.g. 0xFF5733).
    Returns *None* if the input is *None* or 0 (default / no color).
    """
    if not color_int:
        return None
    r = (color_int >> 16) & 0xFF
    g = (color_int >> 8) & 0xFF
    b = color_int & 0xFF
    return f"#{r:02x}{g:02x}{b:02x}"


# -- Persistence helpers -----------------------------------------------------

_SETTINGS_KEY = "appearance/flavor"


def load_saved_flavor() -> str:
    settings = QSettings("Vox", "VoxClient")
    return str(settings.value(_SETTINGS_KEY, "mocha"))


def save_flavor(flavor: str) -> None:
    settings = QSettings("Vox", "VoxClient")
    settings.setValue(_SETTINGS_KEY, flavor)
