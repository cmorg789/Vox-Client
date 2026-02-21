"""HSL hue-based theming system for Vox Client."""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

from PyQt6.QtCore import QSettings


def hsl_to_hex(h: float, s: float, l: float) -> str:
    """Convert HSL (0-360, 0-100, 0-100) to #RRGGBB hex string.

    ``colorsys`` uses HLS order with 0-1 ranges, so we swap s/l and scale.
    """
    r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


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

    # Accent (hue-derived)
    accent: str
    accent_dim: str
    accent_bright: str

    # Role colors (monochromatic tiers)
    role_1: str
    role_2: str
    role_3: str
    role_4: str

    # Status / semantic
    status_success: str
    status_danger: str
    status_warning: str
    status_idle: str
    status_offline: str


class Theme:
    """Generates a full set of theme colors and QSS from a single hue value."""

    def __init__(self, hue: int = 28) -> None:
        self.hue = hue
        self.colors = self._compute_colors(hue)

    @staticmethod
    def _compute_colors(hue: int) -> ThemeColors:
        h = hue
        return ThemeColors(
            # Backgrounds
            bg_deep=hsl_to_hex(h, 20, 4),
            bg_main=hsl_to_hex(h, 18, 7),
            bg_panel=hsl_to_hex(h, 16, 9),
            bg_input=hsl_to_hex(h, 20, 5),
            bg_hover=hsl_to_hex(h, 18, 12),
            bg_active=hsl_to_hex(h, 22, 15),
            # Borders
            border=hsl_to_hex(h, 16, 14),
            border_bright=hsl_to_hex(h, 20, 20),
            # Text
            text_primary=hsl_to_hex(h, 12, 75),
            text_secondary=hsl_to_hex(h, 14, 45),
            text_dim=hsl_to_hex(h, 12, 28),
            # Accent
            accent=hsl_to_hex(h, 70, 50),
            accent_dim=hsl_to_hex(h, 50, 25),
            accent_bright=hsl_to_hex(h, 75, 65),
            # Monochromatic role tiers
            role_1=hsl_to_hex(h, 80, 72),
            role_2=hsl_to_hex(h, 65, 62),
            role_3=hsl_to_hex(h, 50, 52),
            role_4=hsl_to_hex(h, 30, 45),
            # Status / semantic (fixed hex)
            status_success="#409640",
            status_danger="#c63939",
            status_warning="#c6a839",
            status_idle=hsl_to_hex(h, 40, 45),
            status_offline=hsl_to_hex(h, 8, 30),
        )

    def set_hue(self, hue: int) -> None:
        self.hue = hue
        self.colors = self._compute_colors(hue)

    # -- QSS generation ------------------------------------------------------

    def generate_qss(self) -> str:
        c = self.colors
        return f"""
/* Vox Theme – generated from hue {self.hue} */

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
    padding: 6px 8px;
    selection-background-color: {c.accent_dim};
    selection-color: {c.text_primary};
}}

QLineEdit:focus, QTextEdit:focus {{
    border-color: {c.accent_dim};
}}

/* ---------- Buttons ---------- */

QPushButton {{
    background-color: transparent;
    color: {c.accent};
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 6px 14px;
}}

QPushButton:hover {{
    background-color: {c.bg_hover};
    color: {c.accent_bright};
    border-color: {c.accent_dim};
}}

QPushButton:pressed {{
    background-color: {c.accent};
    color: {c.bg_deep};
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
    color: {c.text_dim};
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
    background-color: transparent;
    width: 6px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background-color: {c.border};
    min-height: 20px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {c.border_bright};
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

/* ---------- Slider (hue picker) ---------- */

QSlider::groove:horizontal {{
    border: none;
    height: 4px;
    background: {c.border_bright};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {c.accent};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
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

_SETTINGS_KEY = "theme/hue"


def load_saved_hue() -> int:
    settings = QSettings("Vox", "VoxClient")
    return int(settings.value(_SETTINGS_KEY, 28))


def save_hue(hue: int) -> None:
    settings = QSettings("Vox", "VoxClient")
    settings.setValue(_SETTINGS_KEY, hue)
