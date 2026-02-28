"""Main window – 4-column layout: server strip | channel sidebar | chat | members."""

from __future__ import annotations

import asyncio
import asyncio.base_events
import json
import logging
import mimetypes
import os
import re
import threading
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QVBoxLayout, QWidget
from qasync import asyncSlot

from vox_sdk import Client
from vox_sdk.models.users import PresenceResponse

from vox_client.idle import IdleManager
from vox_client.state import AppState
from vox_client.widgets.ui_helpers import await_dialog

log = logging.getLogger(__name__)


def _save_session(url: str, token: str, user_id: int) -> None:
    s = QSettings("Vox", "VoxClient")
    s.setValue("session/url", url)
    s.setValue("session/token", token)
    s.setValue("session/user_id", user_id)


def _load_session() -> tuple[str, str, int] | None:
    s = QSettings("Vox", "VoxClient")
    url = s.value("session/url")
    token = s.value("session/token")
    user_id = s.value("session/user_id")
    if url and token and user_id is not None:
        return str(url), str(token), int(user_id)
    return None


def _clear_session() -> None:
    s = QSettings("Vox", "VoxClient")
    s.remove("session/url")
    s.remove("session/token")
    s.remove("session/user_id")
    s.remove("last/feed_id")
    s.remove("last/dm_id")


def _is_auth_error(exc: BaseException) -> bool:
    """Return True if *exc* indicates the token is invalid (401/403)."""
    from vox_sdk.errors import VoxHTTPError

    return isinstance(exc, VoxHTTPError) and exc.status in (401, 403)


from vox_client.widgets.channel_sidebar import ChannelSidebar
from vox_client.widgets.chat_header import ChatHeader
from vox_client.widgets.chat_input import ChatInput
from vox_client.widgets.dm_sidebar import DMSidebar
from vox_client.widgets.member_sidebar import MemberSidebar
from vox_client.widgets.message_list import MessageList
from vox_client.widgets.server_strip import ServerStrip
from vox_client.widgets.toast import ToastManager
from vox_client.widgets.user_panel import UserPanel, VoiceStatusBar


class MainWindow(QMainWindow):
    """Primary application window – shown immediately on launch."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Vox")
        self.resize(1100, 700)

        # Restore saved window geometry
        s = QSettings("Vox", "VoxClient")
        geo = s.value("window/geometry")
        if geo is not None:
            self.restoreGeometry(geo)

        self._state = AppState.instance()

        # -- Central widget with HBox --------------------------------
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Left column (server strip + channel sidebar on top, user panel at bottom)
        left_col = QWidget()
        left_col.setFixedWidth(232)  # 52 + 180
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Top row: server strip | channel sidebar
        left_top = QWidget()
        left_top_layout = QHBoxLayout(left_top)
        left_top_layout.setContentsMargins(0, 0, 0, 0)
        left_top_layout.setSpacing(0)

        self._server_strip = ServerStrip()
        left_top_layout.addWidget(self._server_strip)

        self._channel_sidebar = ChannelSidebar()
        left_top_layout.addWidget(self._channel_sidebar)

        self._dm_sidebar = DMSidebar()
        self._dm_sidebar.hide()
        left_top_layout.addWidget(self._dm_sidebar)

        left_layout.addWidget(left_top, stretch=1)

        # Voice status bar (hidden by default, shown when in a voice room)
        self._voice_status_bar = VoiceStatusBar()
        left_layout.addWidget(self._voice_status_bar)

        # User panel spans full 232px width
        self._user_panel = UserPanel()
        left_layout.addWidget(self._user_panel)

        root.addWidget(left_col)

        # 3) Chat main area (stretch) — single bg_main surface
        c = self._state.theme.colors
        chat_col = QWidget()
        chat_col.setObjectName("ChatCol")
        chat_col.setStyleSheet(f"#ChatCol {{ background-color: {c.bg_main}; }}")
        chat_layout = QVBoxLayout(chat_col)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        self._chat_header = ChatHeader()
        chat_layout.addWidget(self._chat_header)

        self._message_list = MessageList()
        chat_layout.addWidget(self._message_list, stretch=1)

        # Typing indicator
        self._typing_label = QLabel()
        self._typing_label.setFixedHeight(18)
        self._typing_label.setStyleSheet(
            f"color: {c.text_dim}; font-size: 11px; padding-left: 16px; "
            f"background-color: {c.bg_main};"
        )
        chat_layout.addWidget(self._typing_label)

        self._chat_input = ChatInput()
        chat_layout.addWidget(self._chat_input)

        root.addWidget(chat_col, stretch=1)

        # 4) Member sidebar (200px)
        self._member_sidebar = MemberSidebar()
        root.addWidget(self._member_sidebar)

        self.setCentralWidget(central)

        # -- Toast notifications -----------------------------------------------
        ToastManager.instance().set_parent(central)

        # -- Typing indicator state --------------------------------------------
        self._typers: dict[int, QTimer] = {}  # user_id → expiry timer
        self._typing_throttle = QTimer()
        self._typing_throttle.setSingleShot(True)

        # -- Wire signals ------------------------------------------------------
        self._channel_sidebar.feed_selected.connect(self._on_feed_selected)
        self._channel_sidebar.room_selected.connect(self._on_room_selected)
        self._channel_sidebar.settings_clicked.connect(self._on_server_settings)
        self._chat_input.message_sent.connect(self._on_send)
        self._chat_input.typing.connect(self._on_local_typing)
        self._user_panel.settings_clicked.connect(self._on_settings)
        self._user_panel.login_clicked.connect(self._on_login_clicked)
        self._voice_status_bar.disconnect_clicked.connect(self._on_voice_disconnect)
        self._state.layout_changed.connect(self._channel_sidebar.populate)
        self._state.voice_state_changed.connect(self._channel_sidebar.populate)
        self._state.typing_started.connect(self._on_remote_typing)
        self._state.presence_updated.connect(self._on_presence_updated)
        self._state.theme_changed.connect(self._on_theme_changed)

        # Drag-and-drop: forward file drops from message list to chat input staging
        self._message_list.file_dropped.connect(self._chat_input._stage_file)

        # DM signals
        self._server_strip.dm_clicked.connect(self._on_dm_mode_enter)
        self._dm_sidebar.dm_selected.connect(self._on_dm_selected)
        self._dm_sidebar.dm_closed.connect(self._on_dm_closed)
        self._state.dm_mode_changed.connect(self._on_dm_mode_changed)
        self._member_sidebar.send_message_requested.connect(self._on_member_send_message)
        self._member_sidebar.open_dm_requested.connect(self.open_dm_with_user)

        # Show logged-out state initially
        self._user_panel.update_user()

    # -- public ----------------------------------------------------------------

    @asyncSlot()
    async def try_restore_session(self) -> None:
        """Attempt to restore a saved session on startup.

        Only clears the saved token on authentication errors (401/403).
        Transient network failures keep the token so the user can retry.
        """
        saved = _load_session()
        if saved is None:
            log.debug("No saved session to restore")
            return
        url, token, user_id = saved
        log.info("Restoring session for user %d at %s", user_id, url)
        try:
            await self._post_login(url, token, user_id)
        except Exception as exc:
            if _is_auth_error(exc):
                log.warning("Session restore failed (auth error), clearing token")
                _clear_session()
            else:
                log.warning("Session restore failed: %s", exc)
                self._show_restore_failed(url, token, user_id, exc)

    def _show_restore_failed(
        self, url: str, token: str, user_id: int, exc: Exception
    ) -> None:
        """Show a non-modal banner with a retry button when session restore
        fails due to a transient error (network down, server unreachable)."""
        c = self._state.theme.colors
        msg = str(exc) or type(exc).__name__

        # Remove any existing banner first
        if hasattr(self, "_restore_banner") and self._restore_banner is not None:
            self._restore_banner.deleteLater()

        banner = QWidget()
        banner.setObjectName("RestoreBanner")
        banner.setStyleSheet(
            f"#RestoreBanner {{ background-color: {c.status_warning}; }}"
        )
        banner.setFixedHeight(32)
        lay = QHBoxLayout(banner)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(8)

        lbl = QLabel(f"Session restore failed: {msg}")
        lbl.setStyleSheet(f"color: {c.bg_deep}; font-size: 11px; border: none;")
        lay.addWidget(lbl, stretch=1)

        from PySide6.QtWidgets import QPushButton

        retry_btn = QPushButton("[ RETRY ]")
        retry_btn.setFixedHeight(22)
        retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        retry_btn.setStyleSheet(
            f"QPushButton {{ color: {c.bg_deep}; font-size: 11px; font-weight: 500; "
            f"border: 1px solid {c.bg_deep}; border-radius: 3px; padding: 2px 10px; "
            f"background: transparent; }}"
            f"QPushButton:hover {{ background-color: {c.bg_deep}; color: {c.status_warning}; }}"
        )
        retry_btn.clicked.connect(lambda: self._retry_restore(url, token, user_id))
        lay.addWidget(retry_btn)

        dismiss_btn = QPushButton("[ DISMISS ]")
        dismiss_btn.setFixedHeight(22)
        dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss_btn.setStyleSheet(
            f"QPushButton {{ color: {c.bg_deep}; font-size: 11px; "
            f"border: none; padding: 2px 6px; background: transparent; }}"
            f"QPushButton:hover {{ text-decoration: underline; }}"
        )
        dismiss_btn.clicked.connect(self._dismiss_restore_banner)
        lay.addWidget(dismiss_btn)

        self._restore_banner = banner

        # Overlay on top of the central widget (don't insert into the layout)
        central = self.centralWidget()
        if central:
            banner.setParent(central)
            banner.raise_()
            banner.setGeometry(0, 0, central.width(), 32)
            banner.show()

    def closeEvent(self, event: object) -> None:
        if hasattr(self, "_idle_manager"):
            self._idle_manager.stop()
        s = QSettings("Vox", "VoxClient")
        s.setValue("window/geometry", self.saveGeometry())
        super().closeEvent(event)

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_restore_banner") and self._restore_banner is not None:
            central = self.centralWidget()
            if central:
                self._restore_banner.setGeometry(0, 0, central.width(), 32)
        ToastManager.instance().reposition()

    def _dismiss_restore_banner(self) -> None:
        if hasattr(self, "_restore_banner") and self._restore_banner is not None:
            self._restore_banner.deleteLater()
            self._restore_banner = None

    @asyncSlot()
    async def _retry_restore(self, url: str, token: str, user_id: int) -> None:
        self._dismiss_restore_banner()
        try:
            await self._post_login(url, token, user_id)
        except Exception as exc:
            if _is_auth_error(exc):
                _clear_session()
            else:
                self._show_restore_failed(url, token, user_id, exc)

    # -- public ----------------------------------------------------------------

    def populate(self) -> None:
        """Populate all panels from cached state data (call after load_server_data)."""
        if self._state._layout is None:
            return
        self._server_strip.populate()
        self._channel_sidebar.populate()
        self._user_panel.update_user()
        self._member_sidebar.refresh()

        # Auto-select last viewed feed (or first available)
        state = self._state
        if state._feeds:
            saved = QSettings("Vox", "VoxClient").value("last/feed_id")
            if saved is not None:
                saved = int(saved)
            if saved and saved in state._feeds:
                feed_id = saved
            else:
                # Pick the first text feed by position
                feed_id = next(iter(state._feeds))
            self._channel_sidebar._on_channel_clicked(feed_id, "feed")

    # -- slots -----------------------------------------------------------------

    @asyncSlot()
    async def _on_login_clicked(self) -> None:
        from vox_client.views.login import LoginDialog

        dlg = LoginDialog(self)
        await await_dialog(dlg)

        if dlg.client is None:
            return

        url = dlg._client_url or ""
        await self._post_login(url, dlg.token, dlg.user_id)
        _save_session(url, dlg.token, dlg.user_id)

    async def _post_login(self, url: str, token: str, user_id: int) -> None:
        """Common post-login sequence: set state, connect gateway, load data."""
        log.info("Connecting to %s as user %d", url, user_id)
        client = Client(url)
        client.http.token = token

        state = self._state
        state.client = client
        state.user_id = user_id

        gateway = await client.connect_gateway()
        state.set_gateway(gateway)

        # Run the gateway on a dedicated asyncio event loop in its own thread
        # to avoid qasync incompatibility with Python 3.14 (_set_nodelay).
        gw_loop = asyncio.new_event_loop()
        self._gw_loop = gw_loop
        gw_ready = threading.Event()

        async def _gw_main() -> None:
            async def _signal_ready() -> None:
                await gateway._ready_event.wait()
                gw_ready.set()

            asyncio.create_task(_signal_ready())
            await gateway.run()

        def _gw_thread() -> None:
            asyncio.set_event_loop(gw_loop)
            gw_loop.run_until_complete(_gw_main())

        t = threading.Thread(target=_gw_thread, daemon=True)
        t.start()

        # Wait for gateway READY before proceeding
        gw_ready.wait(timeout=10)

        # Set initial presence
        try:
            fut = asyncio.run_coroutine_threadsafe(
                gateway.update_presence("online"),
                gw_loop,
            )
            fut.result(timeout=5)
        except Exception:
            log.debug("Failed to set initial presence", exc_info=True)

        # Seed our own presence so the UI shows "Online" immediately
        # (the server's presence_update echo arrives asynchronously).
        state._presences[user_id] = PresenceResponse(
            user_id=user_id,
            status="online",
        )

        # Start idle detection
        self._idle_manager = IdleManager(gw_loop, parent=self)
        self._idle_manager.start()

        log.info("Gateway connected, loading server data")
        await state.load_server_data()
        await state.load_dm_list()
        log.info("Server data loaded, populating UI")
        self.populate()

    @asyncSlot(int)
    async def _on_feed_selected(self, feed_id: int) -> None:
        try:
            self._state.current_feed_id = feed_id
            self._state.current_dm_id = None
            QSettings("Vox", "VoxClient").setValue("last/feed_id", feed_id)
            name = self._state.get_feed_name(feed_id)
            self._chat_header.set_channel(feed_id)
            self._chat_input.set_channel_name(name)
            # Clear typing indicators from previous channel
            for timer in self._typers.values():
                timer.deleteLater()
            self._typers.clear()
            self._typing_label.setText("")
            await self._message_list.load_messages(feed_id)
        except Exception:
            log.error("Failed to select feed %d", feed_id, exc_info=True)

    @asyncSlot(int)
    async def _on_room_selected(self, room_id: int) -> None:
        try:
            state = self._state
            if state.voice_room_id == room_id:
                await state.voice_leave()
            else:
                await state.voice_join(room_id)
        except Exception:
            log.error("Failed to handle room selection %d", room_id, exc_info=True)

    @asyncSlot()
    async def _on_voice_disconnect(self) -> None:
        try:
            await self._state.voice_leave()
        except Exception:
            log.error("Failed to disconnect from voice", exc_info=True)

    @asyncSlot(str, list, str)
    async def _on_send(self, text: str, file_paths: list, embed_url: str = "") -> None:
        if self._state.client is None:
            return

        # Snapshot context for uploads (used to pick upload endpoint)
        dm_id = self._state.current_dm_id
        feed_id = self._state.current_feed_id

        # Upload attachments
        file_ids: list[str] = []
        for path in file_paths:
            mime, _ = mimetypes.guess_type(path)
            mime = mime or "application/octet-stream"
            filename = Path(path).name
            try:
                if dm_id is not None:
                    resp = await self._state.client.files.upload_dm(
                        dm_id, path, filename, mime,
                    )
                elif feed_id is not None:
                    resp = await self._state.client.files.upload(
                        feed_id, path, filename, mime,
                    )
                else:
                    continue
                file_ids.append(resp.file_id)
                # Clean up temp files from clipboard paste after successful upload
                try:
                    import tempfile
                    if path.startswith(tempfile.gettempdir()):
                        os.unlink(path)
                except OSError:
                    pass
            except Exception:
                log.error("Failed to upload file %s", path, exc_info=True)

        # Build optional kwargs
        kwargs: dict = {}
        if file_ids:
            kwargs["attachments"] = file_ids

        # Use explicit embed_url (e.g. from GIF picker), or detect URL in text
        if embed_url:
            kwargs["embed"] = json.dumps({"url": embed_url, "image": embed_url})
        elif text:
            urls = re.findall(r'https?://[^\s<>"\']+', text)
            if urls:
                kwargs["embed"] = json.dumps({"url": urls[0]})

        # Nothing to send (e.g. all uploads failed, no text)
        if not text and not kwargs:
            return

        if dm_id is not None:
            try:
                await self._state.client.dms.send_message(
                    dm_id, body=text or None, **kwargs,
                )
            except Exception:
                log.error("Failed to send DM message to dm %d", dm_id, exc_info=True)
            return
        if feed_id is None:
            return
        try:
            await self._state.client.messages.send(
                feed_id,
                body=text or None,
                attachments=kwargs.get("attachments"),
                embed=kwargs.get("embed"),
            )
        except Exception:
            log.error("Failed to send message to feed %d", feed_id, exc_info=True)

    # -- typing indicator ------------------------------------------------------

    def _on_remote_typing(self, event: object) -> None:
        user_id = getattr(event, "user_id", None)
        if user_id is None:
            return
        # Check if the typing event matches the current context (feed or DM)
        dm_id = getattr(event, "dm_id", None)
        feed_id = getattr(event, "feed_id", None)
        if self._state.current_dm_id is not None:
            if dm_id != self._state.current_dm_id:
                return
        elif feed_id != self._state.current_feed_id:
            return
        # Don't show our own typing
        if user_id == self._state.user_id:
            return
        # Create or reset expiry timer for this typer
        if user_id in self._typers:
            self._typers[user_id].start(5000)
        else:
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda uid=user_id: self._expire_typer(uid))
            timer.start(5000)
            self._typers[user_id] = timer
        self._update_typing_label()

    def _expire_typer(self, user_id: int) -> None:
        timer = self._typers.pop(user_id, None)
        if timer is not None:
            timer.deleteLater()
        self._update_typing_label()

    def _update_typing_label(self) -> None:
        if not self._typers:
            self._typing_label.setText("")
            return
        names = [self._state.get_display_name(uid) for uid in self._typers]
        if len(names) == 1:
            text = f"{names[0]} is typing..."
        elif len(names) == 2:
            text = f"{names[0]} and {names[1]} are typing..."
        else:
            text = f"{names[0]}, {names[1]} and {len(names) - 2} more are typing..."
        self._typing_label.setText(text)

    @asyncSlot()
    async def _on_local_typing(self) -> None:
        if self._typing_throttle.isActive():
            return
        self._typing_throttle.start(5000)
        gw = self._state.gateway
        gw_loop = getattr(self, "_gw_loop", None)
        if gw is None or gw_loop is None:
            return
        dm_id = self._state.current_dm_id
        if dm_id is not None:
            try:
                asyncio.run_coroutine_threadsafe(
                    gw.send("typing_start", {"dm_id": dm_id}),
                    gw_loop,
                )
            except Exception:
                log.debug("Failed to send DM typing indicator", exc_info=True)
            return
        feed_id = self._state.current_feed_id
        if feed_id is not None:
            try:
                asyncio.run_coroutine_threadsafe(
                    gw.send_typing(feed_id),
                    gw_loop,
                )
            except Exception:
                log.debug("Failed to send typing indicator", exc_info=True)

    # -- DM mode ---------------------------------------------------------------

    @asyncSlot()
    async def _on_dm_mode_enter(self) -> None:
        """Enter DM mode: load DM list (emits dm_list_changed → sidebar refreshes)."""
        state = self._state
        if state.client is not None:
            await state.load_dm_list()

        # Auto-select last viewed DM (or first available)
        if state._dms:
            saved = QSettings("Vox", "VoxClient").value("last/dm_id")
            if saved is not None:
                saved = int(saved)
            if saved and saved in state._dms:
                dm_id = saved
            else:
                dm_id = next(iter(state._dms))
            self._dm_sidebar.select_dm(dm_id)

    def _on_dm_mode_changed(self, entering_dm: bool) -> None:
        """Switch between DM mode and server mode."""
        if entering_dm:
            self._channel_sidebar.hide()
            self._dm_sidebar.show()
            self._member_sidebar.hide()
        else:
            self._channel_sidebar.show()
            self._dm_sidebar.hide()
            self._member_sidebar.show()
            # Re-select the last viewed feed
            state = self._state
            if state._feeds:
                saved = QSettings("Vox", "VoxClient").value("last/feed_id")
                if saved is not None:
                    saved = int(saved)
                if saved and saved in state._feeds:
                    feed_id = saved
                else:
                    feed_id = next(iter(state._feeds))
                self._channel_sidebar._on_channel_clicked(feed_id, "feed")

    @asyncSlot(int)
    async def _on_dm_selected(self, dm_id: int) -> None:
        """Handle selection of a DM conversation."""
        try:
            state = self._state
            state.current_dm_id = dm_id
            state.current_feed_id = None
            QSettings("Vox", "VoxClient").setValue("last/dm_id", dm_id)
            name = state.get_dm_display_name(dm_id)
            self._chat_header.set_dm(dm_id)
            self._chat_input.set_dm_name(name)
            # Clear typing indicators from previous context
            for timer in self._typers.values():
                timer.deleteLater()
            self._typers.clear()
            self._typing_label.setText("")
            await self._message_list.load_dm_messages(dm_id)
        except Exception:
            log.error("Failed to select DM %d", dm_id, exc_info=True)

    def _on_dm_closed(self, dm_id: int) -> None:
        """Clear chat area when the active DM is closed."""
        state = self._state
        if state.current_dm_id == dm_id:
            state.current_dm_id = None
            self._chat_header.clear()
            self._chat_input.set_channel_name("")
            self._message_list._clear()

    def open_dm_with_user(self, dm_id: int) -> None:
        """Switch to DM mode and select a specific conversation (used by member sidebar)."""
        state = self._state
        if not state._dm_mode:
            state._dm_mode = True
            state.dm_mode_changed.emit(True)
            self._server_strip._dm_active = True
            self._server_strip.populate()
        self._dm_sidebar.refresh()
        self._dm_sidebar.select_dm(dm_id)

    @asyncSlot(int)
    async def _on_member_send_message(self, user_id: int) -> None:
        """Open or create a DM with a user from the member sidebar."""
        state = self._state
        if state.client is None:
            return
        try:
            dm = await state.client.dms.open(recipient_id=user_id)
            state._dms[dm.dm_id] = dm
            state.dm_list_changed.emit()
            self.open_dm_with_user(dm.dm_id)
        except Exception:
            log.error("Failed to open DM with user %d", user_id, exc_info=True)

    # -- presence --------------------------------------------------------------

    def _on_presence_updated(self, event: object) -> None:
        uid = getattr(event, "user_id", None)
        if uid == self._state.user_id:
            self._user_panel.update_user()

    # -- theme -----------------------------------------------------------------

    def _on_theme_changed(self) -> None:
        """Re-apply inline styles on all widgets after a hue change."""
        c = self._state.theme.colors

        # Container-level inline styles
        self._server_strip.restyle()
        self._channel_sidebar.restyle()
        self._dm_sidebar.restyle()
        self._voice_status_bar.restyle()
        self._user_panel.restyle()
        self._member_sidebar.restyle()
        self._chat_header.restyle()
        self._chat_input.restyle()
        self._message_list.restyle()

        # Chat column background
        chat_col = self.findChild(QWidget, "ChatCol")
        if chat_col is not None:
            chat_col.setStyleSheet(f"#ChatCol {{ background-color: {c.bg_main}; }}")

        # Typing indicator
        self._typing_label.setStyleSheet(
            f"color: {c.text_dim}; font-size: 11px; padding-left: 16px; "
            f"background-color: {c.bg_main};"
        )

        # Rebuild child widgets (they pick up new colors at construction time)
        self._server_strip.populate()
        self._channel_sidebar.populate()
        self._dm_sidebar.refresh()
        self._member_sidebar.refresh()
        self._user_panel.update_user()

    @asyncSlot()
    async def _on_settings(self) -> None:
        """Open user settings dialog."""
        from vox_client.widgets.user_settings import UserSettingsDialog

        dlg = UserSettingsDialog(self)
        dlg.logout_requested.connect(self._on_logout)
        await await_dialog(dlg)

    @asyncSlot()
    async def _on_logout(self) -> None:
        """Clear session and reset to logged-out state."""
        if hasattr(self, "_idle_manager"):
            self._idle_manager.stop()
        state = self._state
        # Leave voice room if connected
        await state.voice_leave()
        _clear_session()
        state.client = None
        state.gateway = None
        state.user_id = None
        state.current_feed_id = None
        state.current_dm_id = None
        state._dm_mode = False
        state._dms.clear()
        state._members.clear()
        state._roles.clear()
        state._presences.clear()
        state._feeds.clear()
        state._rooms.clear()
        state._voice_room_members.clear()
        state._layout = None
        self._user_panel.update_user()
        self._member_sidebar.refresh()
        self._channel_sidebar.populate()
        self._dm_sidebar.refresh()
        # Ensure we're back in server mode
        self._channel_sidebar.show()
        self._dm_sidebar.hide()
        self._member_sidebar.show()

    @asyncSlot()
    async def _on_server_settings(self) -> None:
        """Open server settings dialog."""
        from vox_client.widgets.server_settings import ServerSettingsDialog

        dlg = ServerSettingsDialog(self)
        await await_dialog(dlg)

        # Refresh sidebar header in case server name changed
        self._channel_sidebar.populate()
