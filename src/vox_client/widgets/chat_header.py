"""Chat header – displays current channel name and topic."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel

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
            f"color: {c.text_primary}; font-weight: bold; font-size: 13px;"
        )
        layout.addWidget(self._channel_label)

        self._divider = QLabel("\u2502")
        self._divider.setStyleSheet(f"color: {c.border_bright}; font-size: 13px;")
        self._divider.hide()
        layout.addWidget(self._divider)

        self._topic_label = QLabel()
        self._topic_label.setStyleSheet(f"color: {c.text_dim}; font-size: 12px;")
        self._topic_label.hide()
        layout.addWidget(self._topic_label, stretch=1)

        layout.addStretch()

    def set_channel(self, feed_id: int) -> None:
        """Update header for the given feed."""
        state = AppState.instance()
        name = state.get_feed_name(feed_id)
        topic = state.get_feed_topic(feed_id)

        self._channel_label.setText(f"# {name}")

        if topic:
            self._divider.show()
            self._topic_label.setText(topic)
            self._topic_label.show()
        else:
            self._divider.hide()
            self._topic_label.hide()

    def clear(self) -> None:
        self._channel_label.setText("")
        self._divider.hide()
        self._topic_label.hide()
