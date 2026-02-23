"""Shared icon utility – load SVG files as tinted QIcons."""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer


def tinted_icon(svg_path: Path, color: str, size: int = 16) -> QIcon:
    """Load an SVG and return a QIcon with paths filled in *color*."""
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
