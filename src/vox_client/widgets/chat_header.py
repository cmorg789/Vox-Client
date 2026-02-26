"""Chat header – displays current channel name and topic."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt

log = logging.getLogger(__name__)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from vox_client.state import AppState


class ChatHeader(QFrame):
    """Top bar of the chat area showing ``# channel_name | topic``."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(40)

        state = AppState.instance()
        c = state.theme.colors

        self.setObjectName("ChatHeader")
        self.setStyleSheet(
            f"#ChatHeader {{ background-color: {c.bg_main}; "
            f"border-bottom: 1px solid {c.border}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        self._channel_label = QLabel()
        self._channel_label.setStyleSheet(
            f"color: {c.text_primary}; font-weight: 600; font-size: 13px;"
        )
        layout.addWidget(self._channel_label)

        self._divider = QLabel("\u2502")
        self._divider.setStyleSheet(f"color: {c.border_bright}; font-size: 13px;")
        self._divider.hide()
        layout.addWidget(self._divider)

        self._topic_label = QLabel()
        self._topic_label.setStyleSheet(f"color: {c.text_dim}; font-size: 11px;")
        self._topic_label.hide()
        layout.addWidget(self._topic_label, stretch=1)

        layout.addStretch()

    def restyle(self) -> None:
        """Re-apply inline styles after a theme change."""
        c = AppState.instance().theme.colors
        self.setStyleSheet(
            f"#ChatHeader {{ background-color: {c.bg_main}; "
            f"border-bottom: 1px solid {c.border}; }}"
        )
        self._channel_label.setStyleSheet(
            f"color: {c.text_primary}; font-weight: 600; font-size: 13px;"
        )
        self._divider.setStyleSheet(f"color: {c.border_bright}; font-size: 13px;")
        self._topic_label.setStyleSheet(f"color: {c.text_dim}; font-size: 11px;")

    def set_channel(self, feed_id: int) -> None:
        """Update header for the given feed."""
        state = AppState.instance()
        c = state.theme.colors
        name = state.get_feed_name(feed_id)
        topic = state.get_feed_topic(feed_id)

        self._channel_label.setTextFormat(Qt.TextFormat.RichText)
        self._channel_label.setText(
            f'<span style="color:{c.text_dim}">#</span> {name}'
        )

        if topic:
            self._divider.show()
            self._topic_label.setText(topic)
            self._topic_label.show()
        else:
            self._divider.hide()
            self._topic_label.hide()

    def set_dm(self, dm_id: int) -> None:
        """Update header for a DM conversation."""
        state = AppState.instance()
        c = state.theme.colors
        partner_id = state.get_dm_partner_id(dm_id)
        name = state.get_dm_display_name(dm_id)

        self._channel_label.setTextFormat(Qt.TextFormat.RichText)
        self._channel_label.setText(
            f'<span style="color:{c.text_dim}">@</span> {name}'
        )

        # Show presence as subtitle
        if partner_id is not None:
            presence = state.get_presence(partner_id)
            status = getattr(presence, "status", "offline") if presence else "offline"
            status_labels = {"online": "Online", "idle": "Idle", "dnd": "Do Not Disturb", "offline": "Offline"}
            status_text = status_labels.get(status, "Offline")
            self._divider.show()
            self._topic_label.setText(status_text)
            self._topic_label.show()
        else:
            self._divider.hide()
            self._topic_label.hide()

    def clear(self) -> None:
        self._channel_label.setText("")
        self._divider.hide()
        self._topic_label.hide()
