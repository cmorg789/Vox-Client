"""Hue picker dialog – lets the user change the theme hue at runtime."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from vox_client.state import AppState
from vox_client.theme import save_hue


class HuePickerDialog(QDialog):
    """Modal dialog with a hue slider that live-previews the theme."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Theme")
        self.setFixedSize(320, 120)

        state = AppState.instance()
        c = state.theme.colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Theme Hue")
        title.setStyleSheet(f"color: {c.text_primary}; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 360)
        self._slider.setValue(state.theme.hue)
        self._slider.valueChanged.connect(self._on_hue_changed)
        row_layout.addWidget(self._slider, stretch=1)

        self._value_label = QLabel(str(state.theme.hue))
        self._value_label.setFixedWidth(30)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_label.setStyleSheet(f"color: {c.text_secondary}; font-size: 12px;")
        row_layout.addWidget(self._value_label)

        layout.addWidget(row)

        # Preview swatch
        self._swatch = QWidget()
        self._swatch.setFixedHeight(8)
        self._swatch.setStyleSheet(
            f"background-color: {c.accent}; border-radius: 4px;"
        )
        layout.addWidget(self._swatch)

    def _on_hue_changed(self, value: int) -> None:
        state = AppState.instance()
        state.theme.set_hue(value)
        save_hue(value)
        state.theme_changed.emit()

        c = state.theme.colors
        self._value_label.setText(str(value))
        self._swatch.setStyleSheet(
            f"background-color: {c.accent}; border-radius: 4px;"
        )
