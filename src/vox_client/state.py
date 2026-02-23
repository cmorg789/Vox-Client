"""Global application state and gateway → Qt signal bridge."""

from __future__ import annotations

import asyncio
import logging

from PyQt6.QtCore import QObject, pyqtSignal

from vox_sdk import Client, GatewayClient
from vox_sdk.models.members import MemberResponse
from vox_sdk.models.roles import RoleResponse
from vox_sdk.models.server import FeedInfo, RoomInfo, CategoryInfo, ServerLayoutResponse
from vox_sdk.models.users import PresenceResponse
from vox_sdk.models.voice import VoiceMemberData, VoiceJoinResponse
from vox_sdk.permissions import Permissions

log = logging.getLogger(__name__)

from vox_client.theme import Theme, role_color_for_int


def _log_volume(percent: int) -> float:
    """Convert a linear slider value (0–200) to a perceptual log volume (0.0–2.0).

    Uses an exponential curve so the midpoint (~100) sounds like "half loud"
    rather than half amplitude.  Returns 0.0 for 0% (true silence).
    """
    import math
    if percent <= 0:
        return 0.0
    t = percent / 200.0
    return 2.0 * (math.pow(10, t) - 1) / 9.0


class AppState(QObject):
    """Singleton holding the SDK client, gateway, caches, and bridged signals."""

    # Gateway event signals (payload is the raw event dataclass)
    message_received = pyqtSignal(object)
    message_updated = pyqtSignal(object)
    message_deleted = pyqtSignal(object)
    presence_updated = pyqtSignal(object)
    typing_started = pyqtSignal(object)

    # Member lifecycle signals
    member_joined = pyqtSignal(object)
    member_left = pyqtSignal(object)
    member_updated = pyqtSignal(object)

    # Voice signals
    voice_state_changed = pyqtSignal()       # join/leave/members updated
    voice_connection_error = pyqtSignal(str)  # join failure message

    # UI signals
    layout_loaded = pyqtSignal()
    layout_changed = pyqtSignal()
    theme_changed = pyqtSignal()

    # Thread bridge: carries a callable to execute on the main thread
    _run_on_main = pyqtSignal(object)

    _instance: AppState | None = None

    def __init__(self) -> None:
        super().__init__()
        self.client: Client | None = None
        self.gateway: GatewayClient | None = None
        self.user_id: int | None = None
        self.current_feed_id: int | None = None
        self.theme: Theme | None = None

        # Server name / icon from server.info()
        self.server_name: str = ""
        self.server_icon: str | None = None

        # Caches
        self._members: dict[int, MemberResponse] = {}
        self._roles: dict[int, RoleResponse] = {}
        self._presences: dict[int, PresenceResponse] = {}
        self._feeds: dict[int, FeedInfo] = {}
        self._rooms: dict[int, RoomInfo] = {}
        self._categories: dict[int, CategoryInfo] = {}
        self._layout: ServerLayoutResponse | None = None

        # Voice state
        self.voice_room_id: int | None = None
        self._voice_room_members: dict[int, dict[int, VoiceMemberData]] = {}  # room_id → {user_id → data}
        self._media_client: object | None = None  # VoxMediaClient, lazy-imported
        self.voice_self_mute: bool = False
        self.voice_self_deaf: bool = False
        self._user_volumes: dict[int, float] = {}  # user_id → log volume (session-local)

        # Connect the thread bridge so callables are executed on the main thread
        self._run_on_main.connect(self._execute_on_main)

    # -- singleton -----------------------------------------------------------

    @classmethod
    def instance(cls) -> AppState:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- helpers -------------------------------------------------------------

    def get_display_name(self, user_id: int) -> str:
        member = self._members.get(user_id)
        if member:
            return member.nickname or member.display_name or member.username or str(user_id)
        return str(user_id)

    def get_role_color(self, user_id: int) -> str | None:
        """Return the hex color of the user's highest-positioned role with a color."""
        member = self._members.get(user_id)
        if not member or not member.role_ids:
            return None
        # Find highest positioned role with a color
        best_color: int | None = None
        best_pos = -1
        for rid in member.role_ids:
            role = self._roles.get(rid)
            if role and role.color and role.position > best_pos:
                best_color = role.color
                best_pos = role.position
        return role_color_for_int(best_color)

    def user_has_permission(self, perm: int) -> bool:
        """Check if the current user has the given permission bit(s).

        OR's all permissions from the user's roles and checks against *perm*.
        """
        if self.user_id is None:
            return False
        member = self._members.get(self.user_id)
        if not member or not member.role_ids:
            return False
        combined = 0
        for rid in member.role_ids:
            role = self._roles.get(rid)
            if role and role.permissions is not None:
                combined |= role.permissions
        return Permissions(combined).has(perm)

    def get_presence(self, user_id: int) -> PresenceResponse | None:
        return self._presences.get(user_id)

    def get_feed_name(self, feed_id: int) -> str:
        feed = self._feeds.get(feed_id)
        return feed.name if feed else str(feed_id)

    def get_feed_topic(self, feed_id: int) -> str | None:
        feed = self._feeds.get(feed_id)
        return feed.topic if feed else None

    def get_room_name(self, room_id: int) -> str:
        room = self._rooms.get(room_id)
        return room.name if room else str(room_id)

    def get_voice_members(self, room_id: int) -> dict[int, VoiceMemberData]:
        return self._voice_room_members.get(room_id, {})

    # -- voice ---------------------------------------------------------------

    async def voice_join(self, room_id: int) -> None:
        """Join a voice room. Leaves current room first if needed."""
        assert self.client is not None
        if self.voice_room_id is not None:
            await self.voice_leave()
        try:
            resp: VoiceJoinResponse = await self.client.voice.join(
                room_id, self_mute=self.voice_self_mute, self_deaf=self.voice_self_deaf,
            )
            self.voice_room_id = room_id
            self._voice_room_members[room_id] = {m.user_id: m for m in resp.members}
            # Start media client if the native extension is available
            try:
                from vox_sdk._media import VoxMediaClient
                # Fetch SFU cert for pinning (self-signed by default)
                cert_der = None
                cert_resp = await self.client.voice.get_media_cert()
                if cert_resp is not None:
                    cert_der = bytes(cert_resp.cert_der)
                mc = VoxMediaClient()
                mc.start()
                mc.set_mute(self.voice_self_mute)
                mc.set_deaf(self.voice_self_deaf)
                # Apply saved AV settings
                from PyQt6.QtCore import QSettings
                settings = QSettings("Vox", "VoxClient")
                input_vol = settings.value("av/input_volume", 100, type=int)
                output_vol = settings.value("av/output_volume", 100, type=int)
                gate = settings.value("av/noise_gate", 30, type=int)
                mc.set_input_volume(_log_volume(input_vol))
                mc.set_output_volume(_log_volume(output_vol))
                mc.set_noise_gate(gate / 100.0)
                mc.connect(
                    url=resp.media_url,
                    token=resp.media_token,
                    room_id=room_id,
                    user_id=self.user_id,
                    cert_der=cert_der,
                )
                self._media_client = mc
            except ImportError:
                log.warning("vox_media not available – audio disabled")
            self.voice_state_changed.emit()
        except Exception as exc:
            log.error("Failed to join voice room %d: %s", room_id, exc)
            self.voice_connection_error.emit(str(exc))

    async def voice_leave(self) -> None:
        """Leave the current voice room."""
        if self.voice_room_id is None:
            return
        room_id = self.voice_room_id
        # Disconnect and stop media client
        if self._media_client is not None:
            try:
                self._media_client.disconnect()
                self._media_client.stop()
            except Exception:
                pass
            self._media_client = None
        # Tell server we're leaving
        if self.client is not None:
            try:
                await self.client.voice.leave(room_id)
            except Exception:
                pass
        self.voice_room_id = None
        self.voice_state_changed.emit()

    def voice_set_mute(self, muted: bool) -> None:
        self.voice_self_mute = muted
        if self._media_client is not None:
            try:
                self._media_client.set_mute(muted)
            except Exception:
                pass

    def voice_set_deaf(self, deafened: bool) -> None:
        self.voice_self_deaf = deafened
        if self._media_client is not None:
            try:
                self._media_client.set_deaf(deafened)
            except Exception:
                pass

    def voice_set_input_volume(self, volume: float) -> None:
        if self._media_client is not None:
            try:
                self._media_client.set_input_volume(volume)
            except Exception:
                pass

    def voice_set_output_volume(self, volume: float) -> None:
        if self._media_client is not None:
            try:
                self._media_client.set_output_volume(volume)
            except Exception:
                pass

    def voice_set_noise_gate(self, threshold: float) -> None:
        if self._media_client is not None:
            try:
                self._media_client.set_noise_gate(threshold)
            except Exception:
                pass

    def voice_set_user_volume(self, user_id: int, volume: float) -> None:
        self._user_volumes[user_id] = volume
        if self._media_client is not None:
            try:
                self._media_client.set_user_volume(user_id, volume)
            except Exception:
                pass

    def voice_get_user_volume(self, user_id: int) -> float:
        return self._user_volumes.get(user_id, 1.0)

    async def refresh_layout(self) -> None:
        """Re-fetch the server layout and rebuild all layout caches."""
        assert self.client is not None
        layout = await self.client.server.layout()
        self._layout = layout
        self._feeds = {f.feed_id: f for f in layout.feeds}
        self._rooms = {r.room_id: r for r in layout.rooms}
        self._categories = {c.category_id: c for c in layout.categories}
        self.layout_changed.emit()

    # -- data loading --------------------------------------------------------

    async def load_server_data(self) -> None:
        """Fetch layout + roles + first page of members, populates caches."""
        assert self.client is not None

        # Server info
        info = await self.client.server.info()
        self.server_name = info.name
        self.server_icon = info.icon

        # Layout
        layout = await self.client.server.layout()
        self._layout = layout
        self._feeds = {f.feed_id: f for f in layout.feeds}
        self._rooms = {r.room_id: r for r in layout.rooms}
        self._categories = {c.category_id: c for c in layout.categories}

        # Roles
        roles_resp = await self.client.roles.list()
        self._roles = {r.role_id: r for r in roles_resp.items}

        # Members (first page)
        members_resp = await self.client.members.list(limit=50)
        self._members = {m.user_id: m for m in members_resp.items}

        # Fetch presence for each loaded member (concurrently)
        async def _fetch_presence(uid: int) -> None:
            try:
                p = await self.client.users.get_presence(uid)
                self._presences[uid] = p
            except Exception:
                log.debug("Failed to fetch presence for user %d", uid)

        await asyncio.gather(*[_fetch_presence(uid) for uid in self._members])

        # Fetch voice members for each room concurrently
        async def _fetch_voice_members(rid: int) -> None:
            try:
                resp = await self.client.voice.get_members(rid)
                if resp.members:
                    self._voice_room_members[rid] = {m.user_id: m for m in resp.members}
            except Exception:
                log.debug("Failed to fetch voice members for room %d", rid)

        await asyncio.gather(*[_fetch_voice_members(rid) for rid in self._rooms])

        self.layout_loaded.emit()

    # -- thread bridge -------------------------------------------------------

    def _execute_on_main(self, fn: object) -> None:
        """Run a callable on the main thread (slot for _run_on_main signal)."""
        fn()  # type: ignore[operator]

    # -- gateway setup -------------------------------------------------------

    def set_gateway(self, gw: GatewayClient) -> None:
        self.gateway = gw
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register gateway event handlers.

        All handlers run on the gateway thread so they must NOT touch
        shared state directly.  Instead they schedule a callable via
        ``_run_on_main`` which is delivered to the Qt main thread through
        a queued signal connection.  The callable updates caches and then
        emits the public signal so that UI widgets always see consistent
        state.
        """
        assert self.gateway is not None

        @self.gateway.on("message_create")
        async def _on_message_create(event):  # noqa: ANN001
            self._run_on_main.emit(lambda e=event: self.message_received.emit(e))

        @self.gateway.on("message_update")
        async def _on_message_update(event):  # noqa: ANN001
            self._run_on_main.emit(lambda e=event: self.message_updated.emit(e))

        @self.gateway.on("message_delete")
        async def _on_message_delete(event):  # noqa: ANN001
            self._run_on_main.emit(lambda e=event: self.message_deleted.emit(e))

        @self.gateway.on("presence_update")
        async def _on_presence_update(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                uid = getattr(e, "user_id", None)
                if uid is not None:
                    self._presences[uid] = PresenceResponse(
                        user_id=uid,
                        status=getattr(e, "status", "offline"),
                        custom_status=getattr(e, "custom_status", None),
                        activity=getattr(e, "activity", None),
                    )
                self.presence_updated.emit(e)
            self._run_on_main.emit(_apply)

        @self.gateway.on("typing_start")
        async def _on_typing_start(event):  # noqa: ANN001
            self._run_on_main.emit(lambda e=event: self.typing_started.emit(e))

        @self.gateway.on("member_join")
        async def _on_member_join(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                uid = getattr(e, "user_id", None)
                if uid is not None:
                    self._members[uid] = MemberResponse(
                        user_id=uid,
                        username=getattr(e, "username", ""),
                        display_name=getattr(e, "display_name", None),
                    )
                self.member_joined.emit(e)
            self._run_on_main.emit(_apply)

        @self.gateway.on("member_leave")
        async def _on_member_leave(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                uid = getattr(e, "user_id", None)
                if uid is not None:
                    self._members.pop(uid, None)
                    self._presences.pop(uid, None)
                self.member_left.emit(e)
            self._run_on_main.emit(_apply)

        @self.gateway.on("member_update")
        async def _on_member_update(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                uid = getattr(e, "user_id", None)
                if uid is not None and uid in self._members:
                    nick = getattr(e, "nickname", None)
                    if nick is not None:
                        old = self._members[uid]
                        self._members[uid] = MemberResponse(
                            user_id=old.user_id,
                            display_name=old.display_name,
                            avatar=old.avatar,
                            nickname=nick,
                            role_ids=old.role_ids,
                        )
                self.member_updated.emit(e)
            self._run_on_main.emit(_apply)

        @self.gateway.on("role_assign")
        async def _on_role_assign(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                uid = getattr(e, "user_id", None)
                rid = getattr(e, "role_id", None)
                if uid and rid and uid in self._members:
                    member = self._members[uid]
                    if rid not in member.role_ids:
                        member.role_ids.append(rid)
                self.member_updated.emit(e)
            self._run_on_main.emit(_apply)

        @self.gateway.on("role_revoke")
        async def _on_role_revoke(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                uid = getattr(e, "user_id", None)
                rid = getattr(e, "role_id", None)
                if uid and rid and uid in self._members:
                    member = self._members[uid]
                    if rid in member.role_ids:
                        member.role_ids.remove(rid)
                self.member_updated.emit(e)
            self._run_on_main.emit(_apply)

        # -- Feed/Room/Category CRUD → layout_changed --------------------------

        @self.gateway.on("feed_create")
        async def _on_feed_create(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                feed = FeedInfo(
                    feed_id=e.feed_id,
                    name=e.name,
                    type=e.type or "text",
                    topic=getattr(e, "topic", None),
                    category_id=getattr(e, "category_id", None),
                )
                self._feeds[feed.feed_id] = feed
                if self._layout is not None:
                    self._layout.feeds.append(feed)
                self.layout_changed.emit()
            self._run_on_main.emit(_apply)

        @self.gateway.on("feed_update")
        async def _on_feed_update(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                fid = e.feed_id
                if fid in self._feeds:
                    old = self._feeds[fid]
                    extra = getattr(e, "extra", {})
                    self._feeds[fid] = old.model_copy(update=extra)
                    if self._layout is not None:
                        self._layout.feeds = [
                            self._feeds[fid] if f.feed_id == fid else f
                            for f in self._layout.feeds
                        ]
                self.layout_changed.emit()
            self._run_on_main.emit(_apply)

        @self.gateway.on("feed_delete")
        async def _on_feed_delete(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                fid = e.feed_id
                self._feeds.pop(fid, None)
                if self._layout is not None:
                    self._layout.feeds = [f for f in self._layout.feeds if f.feed_id != fid]
                self.layout_changed.emit()
            self._run_on_main.emit(_apply)

        @self.gateway.on("room_create")
        async def _on_room_create(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                room = RoomInfo(
                    room_id=e.room_id,
                    name=e.name,
                    type=e.type or "voice",
                    category_id=getattr(e, "category_id", None),
                )
                self._rooms[room.room_id] = room
                if self._layout is not None:
                    self._layout.rooms.append(room)
                self.layout_changed.emit()
            self._run_on_main.emit(_apply)

        @self.gateway.on("room_update")
        async def _on_room_update(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                rid = e.room_id
                if rid in self._rooms:
                    old = self._rooms[rid]
                    extra = getattr(e, "extra", {})
                    self._rooms[rid] = old.model_copy(update=extra)
                    if self._layout is not None:
                        self._layout.rooms = [
                            self._rooms[rid] if r.room_id == rid else r
                            for r in self._layout.rooms
                        ]
                self.layout_changed.emit()
            self._run_on_main.emit(_apply)

        @self.gateway.on("room_delete")
        async def _on_room_delete(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                rid = e.room_id
                self._rooms.pop(rid, None)
                self._voice_room_members.pop(rid, None)
                if self._layout is not None:
                    self._layout.rooms = [r for r in self._layout.rooms if r.room_id != rid]
                # If we're in this room, force-disconnect
                if rid == self.voice_room_id:
                    if self._media_client is not None:
                        try:
                            self._media_client.disconnect()
                            self._media_client.stop()
                        except Exception:
                            pass
                        self._media_client = None
                    self.voice_room_id = None
                    self.voice_state_changed.emit()
                self.layout_changed.emit()
            self._run_on_main.emit(_apply)

        @self.gateway.on("category_create")
        async def _on_category_create(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                cat = CategoryInfo(
                    category_id=e.category_id,
                    name=e.name,
                    position=getattr(e, "position", 0) or 0,
                )
                self._categories[cat.category_id] = cat
                if self._layout is not None:
                    self._layout.categories.append(cat)
                self.layout_changed.emit()
            self._run_on_main.emit(_apply)

        @self.gateway.on("category_update")
        async def _on_category_update(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                cid = e.category_id
                if cid in self._categories:
                    old = self._categories[cid]
                    extra = getattr(e, "extra", {})
                    self._categories[cid] = old.model_copy(update=extra)
                    if self._layout is not None:
                        self._layout.categories = [
                            self._categories[cid] if ct.category_id == cid else ct
                            for ct in self._layout.categories
                        ]
                self.layout_changed.emit()
            self._run_on_main.emit(_apply)

        @self.gateway.on("category_delete")
        async def _on_category_delete(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                cid = e.category_id
                self._categories.pop(cid, None)
                if self._layout is not None:
                    self._layout.categories = [
                        ct for ct in self._layout.categories if ct.category_id != cid
                    ]
                self.layout_changed.emit()
            self._run_on_main.emit(_apply)

        # -- Voice gateway events -----------------------------------------------

        @self.gateway.on("voice_state_update")
        async def _on_voice_state_update(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                rid = getattr(e, "room_id", None)
                if rid is None:
                    return
                members_raw = getattr(e, "members", [])
                members = {}
                for m in members_raw:
                    if isinstance(m, dict):
                        vm = VoiceMemberData.model_validate(m)
                    else:
                        vm = m
                    members[vm.user_id] = vm
                if members:
                    self._voice_room_members[rid] = members
                else:
                    self._voice_room_members.pop(rid, None)
                self.voice_state_changed.emit()
            self._run_on_main.emit(_apply)

        @self.gateway.on("media_token_refresh")
        async def _on_media_token_refresh(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                rid = getattr(e, "room_id", None)
                if rid == self.voice_room_id and self._media_client is not None:
                    token = getattr(e, "media_token", None)
                    if token:
                        try:
                            self._media_client.reconnect(token)
                        except Exception:
                            log.warning("Failed to reconnect media client with new token")
            self._run_on_main.emit(_apply)
