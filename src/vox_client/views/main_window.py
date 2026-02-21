"""Main window – 4-column layout: server strip | channel sidebar | chat | members."""

from __future__ import annotations

import asyncio
import asyncio.base_events

from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QVBoxLayout, QWidget
from qasync import asyncSlot

from vox_sdk import Client

from vox_client.state import AppState


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
from vox_client.widgets.channel_sidebar import ChannelSidebar
from vox_client.widgets.chat_header import ChatHeader
from vox_client.widgets.chat_input import ChatInput
from vox_client.widgets.member_sidebar import MemberSidebar
from vox_client.widgets.message_list import MessageList
from vox_client.widgets.server_strip import ServerStrip
from vox_client.widgets.user_panel import UserPanel


class MainWindow(QMainWindow):
    """Primary application window – shown immediately on launch."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Vox")
        self.resize(1100, 700)

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

        left_layout.addWidget(left_top, stretch=1)

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

        # -- Typing indicator state --------------------------------------------
        self._typers: dict[int, QTimer] = {}  # user_id → expiry timer
        self._typing_throttle = QTimer()
        self._typing_throttle.setSingleShot(True)

        # -- Wire signals ------------------------------------------------------
        self._channel_sidebar.feed_selected.connect(self._on_feed_selected)
        self._channel_sidebar.settings_clicked.connect(self._on_server_settings)
        self._chat_input.message_sent.connect(self._on_send)
        self._chat_input.typing.connect(self._on_local_typing)
        self._user_panel.settings_clicked.connect(self._on_settings)
        self._user_panel.login_clicked.connect(self._on_login_clicked)
        self._state.layout_changed.connect(self._channel_sidebar.populate)
        self._state.typing_started.connect(self._on_remote_typing)
        self._state.presence_updated.connect(self._on_presence_updated)

        # Show logged-out state initially
        self._user_panel.update_user()

    # -- public ----------------------------------------------------------------

    @asyncSlot()
    async def try_restore_session(self) -> None:
        """Attempt to restore a saved session on startup."""
        saved = _load_session()
        if saved is None:
            return
        url, token, user_id = saved
        try:
            await self._post_login(url, token, user_id)
        except Exception:
            _clear_session()

    # -- public ----------------------------------------------------------------

    def populate(self) -> None:
        """Populate all panels from cached state data (call after load_server_data)."""
        if self._state._layout is None:
            return
        self._server_strip.populate()
        self._channel_sidebar.populate()
        self._user_panel.update_user()
        self._member_sidebar.refresh()

    # -- slots -----------------------------------------------------------------

    @asyncSlot()
    async def _on_login_clicked(self) -> None:
        from vox_client.views.login import LoginDialog

        dlg = LoginDialog(self)
        dlg.setModal(True)
        dlg.show()

        # Wait for the dialog to close (async-friendly)
        future: asyncio.Future[None] = asyncio.get_event_loop().create_future()
        dlg.finished.connect(lambda _result: future.set_result(None))
        await future

        if dlg.client is None:
            return

        url = dlg._client_url or ""
        await self._post_login(url, dlg.token, dlg.user_id)
        _save_session(url, dlg.token, dlg.user_id)

    async def _post_login(self, url: str, token: str, user_id: int) -> None:
        """Common post-login sequence: set state, connect gateway, load data."""
        client = Client(url)
        client.http.token = token

        state = self._state
        state.client = client
        state.user_id = user_id

        gateway = await client.connect_gateway()
        state.set_gateway(gateway)

        # Python 3.14 + qasync: _set_nodelay raises OSError on sockets managed
        # by Qt's selector.  Patch only for the gateway task so httpx is unaffected.
        _orig = asyncio.base_events._set_nodelay

        async def _run_gateway() -> None:
            asyncio.base_events._set_nodelay = lambda _sock: None
            try:
                await gateway.run()
            finally:
                asyncio.base_events._set_nodelay = _orig

        asyncio.create_task(_run_gateway())

        # Set initial presence
        try:
            await gateway.update_presence("online")
        except Exception:
            pass  # Non-critical if gateway hasn't connected yet

        await state.load_server_data()
        self.populate()

    @asyncSlot(int)
    async def _on_feed_selected(self, feed_id: int) -> None:
        self._state.current_feed_id = feed_id
        name = self._state.get_feed_name(feed_id)
        self._chat_header.set_channel(feed_id)
        self._chat_input.set_channel_name(name)
        # Clear typing indicators from previous channel
        for timer in self._typers.values():
            timer.deleteLater()
        self._typers.clear()
        self._typing_label.setText("")
        await self._message_list.load_messages(feed_id)

    @asyncSlot(str)
    async def _on_send(self, text: str) -> None:
        feed_id = self._state.current_feed_id
        if feed_id is None or self._state.client is None:
            return
        await self._state.client.messages.send(feed_id, body=text)

    # -- typing indicator ------------------------------------------------------

    def _on_remote_typing(self, event: object) -> None:
        feed_id = getattr(event, "feed_id", None)
        user_id = getattr(event, "user_id", None)
        if feed_id != self._state.current_feed_id or user_id is None:
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
        feed_id = self._state.current_feed_id
        if feed_id is not None and self._state.gateway is not None:
            await self._state.gateway.send_typing(feed_id)

    # -- presence --------------------------------------------------------------

    def _on_presence_updated(self, event: object) -> None:
        uid = getattr(event, "user_id", None)
        if uid == self._state.user_id:
            self._user_panel.update_user()

    def _on_settings(self) -> None:
        """Open hue picker dialog."""
        from vox_client.widgets.hue_picker import HuePickerDialog

        dlg = HuePickerDialog(self)
        dlg.exec()

    @asyncSlot()
    async def _on_server_settings(self) -> None:
        """Open server settings dialog."""
        from vox_client.widgets.server_settings import ServerSettingsDialog

        dlg = ServerSettingsDialog(self)
        dlg.setModal(True)
        dlg.show()

        future: asyncio.Future[None] = asyncio.get_event_loop().create_future()
        dlg.finished.connect(lambda _result: future.set_result(None))
        await future

        # Refresh sidebar header in case server name changed
        self._channel_sidebar.populate()
