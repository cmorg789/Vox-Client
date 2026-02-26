"""Toast notification system – bottom-center stacking pills."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from vox_client.state import AppState

# Variant → dot color token
_DOT_COLORS: dict[str, str] = {
    "success": "status_success",
    "error": "status_danger",
    "warning": "status_warning",
    "info": "accent",
}

TOAST_WIDTH = 320


class ToastWidget(QWidget):
    """Individual toast pill."""

    def __init__(
        self,
        message: str,
        kind: str = "error",
        manager: ToastManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        c = AppState.instance().theme.colors

        self.setFixedWidth(TOAST_WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("Toast")
        self.setStyleSheet(
            f"#Toast {{ background-color: {c.bg_panel}; "
            f"border: 1px solid {c.border}; "
            f"border-radius: 4px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(6)

        # Colored dot
        dot_color = getattr(c, _DOT_COLORS.get(kind, "accent"))
        dot = QLabel("\u25cf")
        dot.setFixedWidth(12)
        dot.setStyleSheet(
            f"color: {dot_color}; font-size: 10px; border: none; background: transparent;"
        )
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(dot)

        # Message
        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 12px; border: none; background: transparent;"
        )
        layout.addWidget(msg, stretch=1)

        # Close button
        close = QLabel("\u00d7")
        close.setFixedWidth(14)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(
            f"color: {c.text_dim}; font-size: 14px; border: none; background: transparent;"
        )
        close.setAlignment(Qt.AlignmentFlag.AlignCenter)
        close.mousePressEvent = lambda _ev: self.dismiss()
        layout.addWidget(close)

        self.adjustSize()

        # Auto-dismiss after 3 seconds
        QTimer.singleShot(3000, self.dismiss)

    def dismiss(self) -> None:
        if self._manager is not None:
            self._manager._remove(self)
        self.deleteLater()


class ToastManager:
    """Singleton managing the toast stack."""

    _instance: ToastManager | None = None

    def __init__(self) -> None:
        self._parent: QWidget | None = None
        self._toasts: list[ToastWidget] = []

    @classmethod
    def instance(cls) -> ToastManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_parent(self, widget: QWidget) -> None:
        self._parent = widget

    def show(self, message: str, kind: str = "error") -> None:
        if self._parent is None:
            return
        toast = ToastWidget(message, kind, manager=self, parent=self._parent)
        self._toasts.append(toast)
        toast.show()
        toast.raise_()
        self._restack()

    def reposition(self) -> None:
        self._restack()

    def _remove(self, toast: ToastWidget) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        # Restack remaining after a brief delay so deleteLater finishes
        QTimer.singleShot(0, self._restack)

    def _restack(self) -> None:
        if self._parent is None:
            return
        parent_w = self._parent.width()
        parent_h = self._parent.height()
        right_margin = 16
        bottom_margin = 16
        gap = 8
        y = parent_h - bottom_margin
        x = parent_w - TOAST_WIDTH - right_margin
        for toast in reversed(self._toasts):
            toast.adjustSize()
            h = toast.sizeHint().height()
            y -= h
            toast.move(x, y)
            toast.raise_()
            y -= gap


def show_toast(message: str, kind: str = "error") -> None:
    """Module-level convenience function."""
    ToastManager.instance().show(message, kind)
