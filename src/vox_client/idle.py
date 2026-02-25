"""Auto-idle presence detection based on user inactivity."""

from __future__ import annotations

import asyncio
import logging
import time

from PyQt6.QtCore import QEvent, QObject, QSettings, QTimer
from PyQt6.QtWidgets import QApplication

from vox_sdk.models.users import PresenceResponse

from vox_client.state import AppState

log = logging.getLogger(__name__)

_ACTIVITY_EVENTS = frozenset({
    QEvent.Type.MouseMove,
    QEvent.Type.MouseButtonPress,
    QEvent.Type.KeyPress,
    QEvent.Type.Wheel,
})

_DEFAULT_TIMEOUT_MINUTES = 5
_CHECK_INTERVAL_MS = 15_000  # 15 seconds


class IdleManager(QObject):
    """Detects user inactivity and toggles presence between online/idle."""

    def __init__(self, gw_loop: asyncio.AbstractEventLoop, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._gw_loop = gw_loop
        self._state = AppState.instance()
        self._last_activity = time.monotonic()
        self._is_idle = False

        s = QSettings("Vox", "VoxClient")
        self._timeout_seconds = s.value("idle/timeout_minutes", _DEFAULT_TIMEOUT_MINUTES, type=int) * 60

        self._timer = QTimer(self)
        self._timer.setInterval(_CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self._check_idle)

        # Reset activity when voice state changes (user is active if in voice)
        self._state.voice_state_changed.connect(self._on_voice_activity)

    def start(self) -> None:
        """Install the event filter and start the idle check timer."""
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._last_activity = time.monotonic()
        self._timer.start()
        log.debug("IdleManager started (timeout=%ds)", self._timeout_seconds)

    def stop(self) -> None:
        """Remove the event filter and stop the timer."""
        self._timer.stop()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        log.debug("IdleManager stopped")

    def set_timeout(self, minutes: int) -> None:
        """Update the idle timeout at runtime."""
        self._timeout_seconds = max(1, minutes) * 60
        s = QSettings("Vox", "VoxClient")
        s.setValue("idle/timeout_minutes", minutes)
        log.debug("Idle timeout updated to %d min", minutes)

    # -- event filter ----------------------------------------------------------

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() in _ACTIVITY_EVENTS:
            self._last_activity = time.monotonic()
            if self._is_idle:
                self._set_active()
        return False

    # -- idle check ------------------------------------------------------------

    def _check_idle(self) -> None:
        if self._is_idle:
            return
        elapsed = time.monotonic() - self._last_activity
        log.debug("Idle check: %.0fs elapsed, threshold=%ds", elapsed, self._timeout_seconds)
        if elapsed >= self._timeout_seconds:
            self._set_idle()

    def _set_idle(self) -> None:
        # Don't override DND
        if self._is_user_dnd():
            return
        self._is_idle = True
        log.info("User idle after %ds of inactivity", self._timeout_seconds)
        self._update_presence("idle")

    def _set_active(self) -> None:
        # Don't override DND
        if self._is_user_dnd():
            self._is_idle = False
            return
        self._is_idle = False
        log.info("User active again")
        self._update_presence("online")

    # -- helpers ---------------------------------------------------------------

    def _is_user_dnd(self) -> bool:
        uid = self._state.user_id
        if uid is None:
            return False
        p = self._state.get_presence(uid)
        return p is not None and p.status == "dnd"

    def _update_presence(self, status: str) -> None:
        state = self._state
        gw = state.gateway
        if gw is None:
            return

        # Update local cache immediately so the UI reflects the change
        # without waiting for the server echo.
        uid = state.user_id
        if uid is not None:
            state._presences[uid] = PresenceResponse(user_id=uid, status=status)
            state.presence_updated.emit(state._presences[uid])

        try:
            asyncio.run_coroutine_threadsafe(
                gw.update_presence(status),
                self._gw_loop,
            )
        except Exception:
            log.debug("Failed to update presence to %s", status, exc_info=True)

    def _on_voice_activity(self) -> None:
        """Reset activity timer when voice state changes (join/leave)."""
        if self._state.voice_room_id is not None:
            self._last_activity = time.monotonic()
            if self._is_idle:
                self._set_active()
