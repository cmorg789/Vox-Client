"""Resource path resolver for both development and frozen (PyInstaller) mode."""

import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "vox_client"
    return Path(__file__).resolve().parent


RESOURCES_DIR = _base_dir() / "resources"
ICONS_DIR = RESOURCES_DIR / "icons"
FONTS_DIR = RESOURCES_DIR / "fonts"
