"""Global application state and gateway → Qt signal bridge."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, QTimer, Signal

from vox_sdk import Client, GatewayClient
from vox_sdk.models.dms import DMResponse
from vox_sdk.models.emoji import EmojiResponse
from vox_sdk.models.members import MemberResponse
from vox_sdk.models.roles import RoleResponse
from vox_sdk.models.server import FeedInfo, RoomInfo, CategoryInfo, ServerLayoutResponse
from vox_sdk.models.users import PresenceResponse
from vox_sdk.models.voice import VoiceMemberData, VoiceJoinResponse
from vox_sdk.permissions import Permissions

log = logging.getLogger(__name__)

from vox_client.theme import Theme, role_color_for_int


def _event_to_msg_dict(event: object) -> dict:
    """Convert a gateway message event to a MessageResponse-shaped dict."""
    return {
        "msg_id": getattr(event, "msg_id", None),
        "feed_id": getattr(event, "feed_id", None),
        "dm_id": getattr(event, "dm_id", None),
        "author_id": getattr(event, "author_id", None),
        "body": getattr(event, "body", None),
        "timestamp": getattr(event, "timestamp", 0),
        "attachments": getattr(event, "attachments", []),
        "embed": getattr(event, "embed", None),
        "edit_timestamp": getattr(event, "edit_timestamp", None),
    }


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
    message_received = Signal(object)
    message_updated = Signal(object)
    message_deleted = Signal(object)
    presence_updated = Signal(object)
    typing_started = Signal(object)

    # Member lifecycle signals
    member_joined = Signal(object)
    member_left = Signal(object)
    member_updated = Signal(object)

    # Voice signals
    voice_state_changed = Signal()       # join/leave/members updated
    voice_connection_error = Signal(str)  # join failure message
    voice_media_event = Signal(str, str)  # (event_type, detail) from media client
    speaking_changed = Signal(int, bool)  # (user_id, is_speaking)

    # Emoji signals
    emoji_changed = Signal()

    # DM signals
    dm_created = Signal(object)
    dm_updated = Signal(object)
    dm_list_changed = Signal()
    dm_mode_changed = Signal(bool)  # True = entering DM mode

    # UI signals
    layout_loaded = Signal()
    layout_changed = Signal()
    theme_changed = Signal()

    # Thread bridge: carries a callable to execute on the main thread
    _run_on_main = Signal(object)

    _instance: AppState | None = None

    def __init__(self) -> None:
        super().__init__()
        self.client: Client | None = None
        self.gateway: GatewayClient | None = None
        self.user_id: int | None = None
        self.current_feed_id: int | None = None
        self.current_dm_id: int | None = None
        self.theme: Theme | None = None

        # Server name / icon from server.info()
        self.server_name: str = ""
        self.server_icon: str | None = None

        # DM state
        self._dms: dict[int, DMResponse] = {}
        self._dm_mode: bool = False

        # Caches
        self._members: dict[int, MemberResponse] = {}
        self._roles: dict[int, RoleResponse] = {}
        self._presences: dict[int, PresenceResponse] = {}
        self._feeds: dict[int, FeedInfo] = {}
        self._rooms: dict[int, RoomInfo] = {}
        self._categories: dict[int, CategoryInfo] = {}
        self._emoji: dict[int, EmojiResponse] = {}
        self._emoji_image_paths: dict[str, str] = {}  # name → local file path
        self._layout: ServerLayoutResponse | None = None

        # Voice state
        self.voice_room_id: int | None = None
        self._voice_room_members: dict[int, dict[int, VoiceMemberData]] = {}  # room_id → {user_id → data}
        self._media_client: object | None = None  # VoxMediaClient, lazy-imported
        self._media_url: str | None = None       # SFU URL for token refresh reconnect
        self._media_cert_der: bytes | None = None
        self.voice_self_mute: bool = False
        self.voice_self_deaf: bool = False
        self._user_volumes: dict[int, float] = {}  # user_id → log volume (session-local)
        self._speaking_users: set[int] = set()  # user_ids currently speaking
        self._media_poll_timer: QTimer | None = None

        # E2EE / MLS
        self._crypto: object | None = None  # CryptoManager, lazy-imported
        self._pending_plaintext: dict[int, deque[str]] = {}  # dm_id → FIFO of plaintexts for own send echoes

        # Connect the thread bridge so callables are executed on the main thread
        self._run_on_main.connect(self._execute_on_main)

    # -- singleton -----------------------------------------------------------

    @classmethod
    def instance(cls) -> AppState:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- E2EE / MLS ----------------------------------------------------------

    @property
    def crypto(self):
        """Return the CryptoManager if available, else None."""
        return self._crypto

    async def init_crypto(self) -> None:
        """Initialise MLS encryption for the current user/device."""
        from vox_sdk.crypto.manager import CryptoManager

        if self.client is None or self.user_id is None:
            return

        import uuid

        from PySide6.QtCore import QSettings

        s = QSettings("Vox", "VoxClient")
        device_id = s.value("mls/device_id")
        if not device_id:
            device_id = str(uuid.uuid4())
            s.setValue("mls/device_id", device_id)

        db_dir = Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        ) / "Vox"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(db_dir / "mls.db")

        crypto = CryptoManager(self.client, db_path=db_path)
        await crypto.initialize(self.user_id, device_id)

        # Register device (ignore conflict if already registered)
        try:
            import platform
            await crypto.register_device(platform.node() or "Vox Desktop")
        except Exception:
            log.debug("Device registration skipped (likely already registered)", exc_info=True)

        try:
            await crypto.refresh_key_packages()
        except Exception:
            log.debug("Key package refresh failed (server may not support E2EE yet)", exc_info=True)

        self._crypto = crypto
        log.info("MLS crypto initialised")

    def decrypt_body(self, d: dict) -> None:
        """If *d* has an opaque_blob but no body, decrypt in-place."""
        blob = d.get("opaque_blob")
        if not blob or d.get("body") is not None:
            return
        # MLS cannot decrypt messages we sent ourselves — use stashed plaintext
        if d.get("author_id") == self.user_id:
            dm_id = d.get("dm_id")
            q = self._pending_plaintext.get(dm_id) if dm_id is not None else None
            if q:
                d["body"] = q.popleft()
                if not q:
                    del self._pending_plaintext[dm_id]
                return
            # No stashed plaintext (other device or already consumed) — fall through
        if self._crypto is None:
            d["body"] = "[Encrypted message]"
            return
        dm_id = d.get("dm_id")
        feed_id = d.get("feed_id")
        try:
            d["body"] = self._crypto.decrypt_message(blob, dm_id=dm_id, feed_id=feed_id)
        except Exception:
            log.debug("Failed to decrypt message %s", d.get("msg_id"), exc_info=True)
            d["body"] = "[Encrypted message]"


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

    def get_custom_emoji(self) -> list[EmojiResponse]:
        """Return all cached custom server emoji."""
        return list(self._emoji.values())

    def get_emoji_image_path(self, name: str) -> str | None:
        """Return local file path for a custom emoji image, or None."""
        return self._emoji_image_paths.get(name)

    def get_voice_members(self, room_id: int) -> dict[int, VoiceMemberData]:
        return self._voice_room_members.get(room_id, {})

    def is_speaking(self, user_id: int) -> bool:
        return user_id in self._speaking_users

    # -- DM helpers ----------------------------------------------------------

    def get_dm_partner_id(self, dm_id: int) -> int | None:
        """Return the other participant's user_id for a 1-on-1 DM."""
        dm = self._dms.get(dm_id)
        if dm is None or dm.is_group or self.user_id is None:
            return None
        for uid in dm.participant_ids:
            if uid != self.user_id:
                return uid
        return None

    def get_dm_display_name(self, dm_id: int) -> str:
        """Return the display name for a DM conversation."""
        dm = self._dms.get(dm_id)
        if dm is None:
            return str(dm_id)
        if dm.is_group and dm.name:
            return dm.name
        partner_id = self.get_dm_partner_id(dm_id)
        if partner_id is not None:
            return self.get_display_name(partner_id)
        return str(dm_id)

    async def load_dm_list(self) -> None:
        """Fetch DMs via client.dms.list() and populate the _dms cache."""
        assert self.client is not None
        try:
            resp = await self.client.dms.list()
            self._dms = {dm.dm_id: dm for dm in resp.items}
            self.dm_list_changed.emit()
        except Exception:
            log.error("Failed to load DM list", exc_info=True)

    # -- voice ---------------------------------------------------------------

    async def voice_join(self, room_id: int) -> None:
        """Join a voice room. Leaves current room first if needed."""
        assert self.client is not None
        if self.voice_room_id is not None:
            await self.voice_leave()
        try:
            log.info("Joining voice room %d", room_id)
            resp: VoiceJoinResponse = await self.client.voice.join(
                room_id, self_mute=self.voice_self_mute, self_deaf=self.voice_self_deaf,
            )
            log.debug("Voice join response: media_url=%s, members=%d",
                       resp.media_url, len(resp.members))
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
                    log.debug("Got SFU cert (%d bytes)", len(cert_der))
                else:
                    log.warning("No SFU cert returned – connecting without cert pinning")
                mc = VoxMediaClient()
                mc.start()
                log.debug("Media client started")
                mc.set_mute(self.voice_self_mute)
                mc.set_deaf(self.voice_self_deaf)
                # Apply saved AV settings
                from PySide6.QtCore import QSettings
                settings = QSettings("Vox", "VoxClient")
                input_vol = settings.value("av/input_volume", 100, type=int)
                output_vol = settings.value("av/output_volume", 100, type=int)
                gate = settings.value("av/noise_gate", 30, type=int)
                log.debug("AV settings: input=%d%% output=%d%% gate=%d%%",
                          input_vol, output_vol, gate)
                mc.set_input_volume(_log_volume(input_vol))
                mc.set_output_volume(_log_volume(output_vol))
                mc.set_noise_gate(gate / 100.0)
                input_dev = settings.value("av/input_device_name")
                output_dev = settings.value("av/output_device_name")
                log.info("Connecting media client to %s (room=%d, user=%d, in=%s, out=%s)",
                         resp.media_url, room_id, self.user_id, input_dev, output_dev)
                mc.connect(
                    url=resp.media_url,
                    token=resp.media_token,
                    room_id=room_id,
                    user_id=self.user_id,
                    cert_der=cert_der,
                    input_device=input_dev,
                    output_device=output_dev,
                )
                self._media_client = mc
                self._media_url = resp.media_url
                self._media_cert_der = cert_der
                self._start_media_poll()
                log.info("Media client connected and polling started")
            except ImportError:
                log.warning("vox_media native extension not available – audio disabled", exc_info=True)
            except Exception:
                log.error("Failed to start media client for room %d", room_id, exc_info=True)
            self.voice_state_changed.emit()
        except Exception as exc:
            log.error("Failed to join voice room %d: %s", room_id, exc, exc_info=True)
            self.voice_connection_error.emit(str(exc))

    async def voice_leave(self) -> None:
        """Leave the current voice room."""
        if self.voice_room_id is None:
            return
        room_id = self.voice_room_id
        log.info("Leaving voice room %d", room_id)
        # Disconnect and stop media client
        self._stop_media_poll()
        if self._media_client is not None:
            try:
                self._media_client.disconnect()
                self._media_client.stop()
                log.debug("Media client stopped for room %d", room_id)
            except Exception:
                log.warning("Error disconnecting media client for room %d", room_id, exc_info=True)
            self._media_client = None
        self._media_url = None
        self._media_cert_der = None
        # Tell server we're leaving
        if self.client is not None:
            try:
                await self.client.voice.leave(room_id)
            except Exception:
                log.warning("Error sending voice leave for room %d", room_id, exc_info=True)
        self.voice_room_id = None
        # Clear speaking state for all users
        for uid in list(self._speaking_users):
            self._speaking_users.discard(uid)
            self.speaking_changed.emit(uid, False)
        self.voice_state_changed.emit()

    def _start_media_poll(self) -> None:
        """Start a 100ms timer that drains events from the media client."""
        self._stop_media_poll()
        timer = QTimer(self)
        timer.setInterval(100)
        timer.timeout.connect(self._poll_media_events)
        timer.start()
        self._media_poll_timer = timer

    def _stop_media_poll(self) -> None:
        if self._media_poll_timer is not None:
            self._media_poll_timer.stop()
            self._media_poll_timer = None

    def _poll_media_events(self) -> None:
        mc = self._media_client
        if mc is None:
            self._stop_media_poll()
            return
        try:
            # Drain all pending events
            while True:
                ev = mc.poll_event()
                if ev is None:
                    break
                event_type, detail = ev
                log.debug("Media event: %s %s", event_type, detail)
                self.voice_media_event.emit(event_type, detail)
                if event_type == "connected":
                    log.info("Media transport connected")
                elif event_type == "connect_failed":
                    log.error("Media connection failed: %s", detail)
                    self.voice_connection_error.emit(f"Media connection failed: {detail}")
                elif event_type == "disconnected":
                    log.warning("Media disconnected: %s", detail)
                    self.voice_connection_error.emit(f"Media disconnected: {detail}")
                elif event_type == "reconnecting":
                    log.info("Media reconnecting: %s", detail)
                elif event_type == "audio_error":
                    log.error("Audio error: %s", detail)
                    self.voice_connection_error.emit(f"Audio error: {detail}")
                elif event_type == "video_error":
                    log.error("Video error: %s", detail)
                elif event_type == "speaking_start":
                    try:
                        uid = int(detail)
                        if uid not in self._speaking_users:
                            self._speaking_users.add(uid)
                            self.speaking_changed.emit(uid, True)
                    except ValueError:
                        pass
                elif event_type == "speaking_stop":
                    try:
                        uid = int(detail)
                        if uid in self._speaking_users:
                            self._speaking_users.discard(uid)
                            self.speaking_changed.emit(uid, False)
                    except ValueError:
                        pass
        except Exception:
            log.error("Error polling media events", exc_info=True)

    def voice_set_mute(self, muted: bool) -> None:
        self.voice_self_mute = muted
        if self._media_client is not None:
            try:
                self._media_client.set_mute(muted)
            except Exception:
                log.warning("Failed to set mute=%s on media client", muted, exc_info=True)

    def voice_set_deaf(self, deafened: bool) -> None:
        self.voice_self_deaf = deafened
        if self._media_client is not None:
            try:
                self._media_client.set_deaf(deafened)
            except Exception:
                log.warning("Failed to set deaf=%s on media client", deafened, exc_info=True)

    def voice_set_input_volume(self, volume: float) -> None:
        if self._media_client is not None:
            try:
                self._media_client.set_input_volume(volume)
            except Exception:
                log.warning("Failed to set input volume on media client", exc_info=True)

    def voice_set_output_volume(self, volume: float) -> None:
        if self._media_client is not None:
            try:
                self._media_client.set_output_volume(volume)
            except Exception:
                log.warning("Failed to set output volume on media client", exc_info=True)

    def voice_set_noise_gate(self, threshold: float) -> None:
        if self._media_client is not None:
            try:
                self._media_client.set_noise_gate(threshold)
            except Exception:
                log.warning("Failed to set noise gate on media client", exc_info=True)

    def voice_set_user_volume(self, user_id: int, volume: float) -> None:
        self._user_volumes[user_id] = volume
        if self._media_client is not None:
            try:
                self._media_client.set_user_volume(user_id, volume)
            except Exception:
                log.warning("Failed to set user volume for %d on media client", user_id, exc_info=True)

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

        await self.load_emoji()

        self.layout_loaded.emit()

    async def load_emoji(self) -> None:
        """Fetch custom server emoji, populate cache, and download images."""
        assert self.client is not None
        try:
            resp = await self.client.emoji.list_emoji()
            self._emoji = {e.emoji_id: e for e in resp.items}
            log.debug("Loaded %d custom emoji", len(self._emoji))
            await self._cache_emoji_images()
        except Exception:
            log.warning("Failed to load custom emoji", exc_info=True)

    def _resolve_image_url(self, url: str) -> str:
        """Resolve a possibly-relative image URL to an absolute one."""
        if url.startswith(("http://", "https://")):
            return url
        # Relative path — prepend the SDK client's base URL
        if self.client is not None:
            return self.client.http.base_url + url
        return url

    async def _cache_emoji_images(self) -> None:
        """Download custom emoji images to a local cache directory."""
        cache_root = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation,
        )
        cache_dir = Path(cache_root) / "emoji"
        cache_dir.mkdir(parents=True, exist_ok=True)

        async def _download(name: str, url: str) -> None:
            ext = Path(url).suffix or ".png"
            dest = cache_dir / f"{name}{ext}"
            log.debug("Emoji cache: %s url=%s ext=%s dest=%s", name, url, ext, dest)
            if dest.exists():
                self._emoji_image_paths[name] = str(dest)
                log.debug("Emoji cache hit: %s -> %s", name, dest)
                return
            try:
                # Use the SDK's httpx client so auth headers and base URL
                # are handled automatically (works with S3 pre-signed URLs too).
                resp = await self.client.http.get(url)
                resp.raise_for_status()
                await asyncio.to_thread(dest.write_bytes, resp.content)
                self._emoji_image_paths[name] = str(dest)
                log.debug("Emoji cached: %s -> %s (%d bytes)", name, dest, len(resp.content))
            except Exception:
                log.debug("Failed to cache emoji image %s from %s", name, url, exc_info=True)

        tasks = []
        for em in self._emoji.values():
            if em.image:
                tasks.append(_download(em.name, em.image))
        if tasks:
            await asyncio.gather(*tasks)

    # -- thread bridge -------------------------------------------------------

    def _execute_on_main(self, fn: object) -> None:
        """Run a callable on the main thread (slot for _run_on_main signal)."""
        try:
            fn()  # type: ignore[operator]
        except Exception:
            log.exception("Error executing gateway callback on main thread")

    # -- gateway setup -------------------------------------------------------

    def set_gateway(self, gw: GatewayClient) -> None:
        log.info("Setting gateway and registering event handlers")
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
            def _apply(e=event):  # noqa: ANN001
                from vox_client.cache import message_cache
                d = _event_to_msg_dict(e)
                key = f"dm:{e.dm_id}" if getattr(e, "dm_id", None) else f"feed:{e.feed_id}"
                message_cache.append(key, d)
                self.message_received.emit(e)
            self._run_on_main.emit(_apply)

        @self.gateway.on("message_update")
        async def _on_message_update(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                from vox_client.cache import message_cache
                key = f"dm:{e.dm_id}" if getattr(e, "dm_id", None) else f"feed:{e.feed_id}"
                message_cache.update(
                    key,
                    getattr(e, "msg_id", 0),
                    getattr(e, "body", "") or "",
                    getattr(e, "edit_timestamp", None),
                )
                self.message_updated.emit(e)
            self._run_on_main.emit(_apply)

        @self.gateway.on("message_delete")
        async def _on_message_delete(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                from vox_client.cache import message_cache
                key = f"dm:{e.dm_id}" if getattr(e, "dm_id", None) else f"feed:{e.feed_id}"
                message_cache.delete(key, getattr(e, "msg_id", 0))
                self.message_deleted.emit(e)
            self._run_on_main.emit(_apply)

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
                    type=e.channel_type or "text",
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
                    type=e.channel_type or "voice",
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
                    self._stop_media_poll()
                    if self._media_client is not None:
                        try:
                            self._media_client.disconnect()
                            self._media_client.stop()
                        except Exception:
                            log.warning("Error stopping media client after room %d deleted", rid, exc_info=True)
                        self._media_client = None
                    self._media_url = None
                    self._media_cert_der = None
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

        # -- Emoji gateway events -----------------------------------------------

        @self.gateway.on("emoji_create")
        async def _on_emoji_create(event):  # noqa: ANN001
            name = getattr(event, "name", "")
            image = getattr(event, "image", None)
            # Download the image in the background before applying to main thread.
            # Gateway handlers run on a dedicated event loop, so use urllib
            # (synchronous, in a thread) instead of the SDK's async httpx client.
            if image and name:
                import urllib.request

                full_url = self._resolve_image_url(image)
                cache_root = QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.CacheLocation,
                )
                cache_dir = Path(cache_root) / "emoji"
                cache_dir.mkdir(parents=True, exist_ok=True)
                ext = Path(image).suffix or ".png"
                dest = cache_dir / f"{name}{ext}"
                try:
                    await asyncio.to_thread(urllib.request.urlretrieve, full_url, dest)
                    self._emoji_image_paths[name] = str(dest)
                except Exception:
                    log.debug("Failed to cache new emoji image %s", name)

            def _apply(e=event):  # noqa: ANN001
                eid = getattr(e, "emoji_id", None)
                if eid is not None:
                    self._emoji[eid] = EmojiResponse(
                        emoji_id=eid,
                        name=getattr(e, "name", ""),
                        creator_id=getattr(e, "creator_id", 0),
                        image=getattr(e, "image", None),
                    )
                self.emoji_changed.emit()
            self._run_on_main.emit(_apply)

        @self.gateway.on("emoji_update")
        async def _on_emoji_update(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                eid = getattr(e, "emoji_id", None)
                if eid is not None and eid in self._emoji:
                    extra = getattr(e, "extra", {})
                    self._emoji[eid] = self._emoji[eid].model_copy(update=extra)
                self.emoji_changed.emit()
            self._run_on_main.emit(_apply)

        @self.gateway.on("emoji_delete")
        async def _on_emoji_delete(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                eid = getattr(e, "emoji_id", None)
                if eid is not None:
                    removed = self._emoji.pop(eid, None)
                    if removed:
                        path = self._emoji_image_paths.pop(removed.name, None)
                        if path:
                            Path(path).unlink(missing_ok=True)
                self.emoji_changed.emit()
            self._run_on_main.emit(_apply)

        # -- Voice gateway events -----------------------------------------------

        @self.gateway.on("voice_state_update")
        async def _on_voice_state_update(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                try:
                    rid = getattr(e, "room_id", None)
                    if rid is None:
                        log.warning("voice_state_update missing room_id")
                        return
                    members_raw = getattr(e, "members", [])
                    members = {}
                    for m in members_raw:
                        if isinstance(m, dict):
                            vm = VoiceMemberData.model_validate(m)
                        else:
                            vm = m
                        members[vm.user_id] = vm
                    log.debug("voice_state_update room=%d members=%d", rid, len(members))
                    if members:
                        self._voice_room_members[rid] = members
                    else:
                        self._voice_room_members.pop(rid, None)
                    self.voice_state_changed.emit()
                except Exception:
                    log.error("Error handling voice_state_update", exc_info=True)
            self._run_on_main.emit(_apply)

        @self.gateway.on("media_token_refresh")
        async def _on_media_token_refresh(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                try:
                    rid = getattr(e, "room_id", None)
                    log.debug("media_token_refresh for room=%s (current=%s)", rid, self.voice_room_id)
                    if rid == self.voice_room_id and self._media_client is not None:
                        token = getattr(e, "media_token", None)
                        if token and self._media_url is not None:
                            from PySide6.QtCore import QSettings as _QS
                            _s = _QS("Vox", "VoxClient")
                            self._media_client.connect(
                                url=self._media_url,
                                token=token,
                                room_id=rid,
                                user_id=self.user_id,
                                cert_der=self._media_cert_der,
                                input_device=_s.value("av/input_device_name"),
                                output_device=_s.value("av/output_device_name"),
                            )
                            log.info("Media client reconnected with refreshed token")
                        else:
                            log.warning("media_token_refresh missing token or media_url "
                                        "(token=%s, url=%s)", bool(token), self._media_url)
                except Exception:
                    log.error("Failed to handle media_token_refresh", exc_info=True)
            self._run_on_main.emit(_apply)

        # -- DM gateway events --------------------------------------------------

        @self.gateway.on("dm_create")
        async def _on_dm_create(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                dm_id = getattr(e, "dm_id", None)
                if dm_id is not None:
                    self._dms[dm_id] = DMResponse(
                        dm_id=dm_id,
                        participant_ids=getattr(e, "participant_ids", []),
                        is_group=getattr(e, "is_group", False),
                        name=getattr(e, "name", None),
                    )
                self.dm_created.emit(e)
                self.dm_list_changed.emit()
            self._run_on_main.emit(_apply)

        @self.gateway.on("dm_update")
        async def _on_dm_update(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                dm_id = getattr(e, "dm_id", None)
                if dm_id is not None and dm_id in self._dms:
                    extra = getattr(e, "extra", {})
                    self._dms[dm_id] = self._dms[dm_id].model_copy(update=extra)
                self.dm_updated.emit(e)
                self.dm_list_changed.emit()
            self._run_on_main.emit(_apply)

        @self.gateway.on("dm_recipient_add")
        async def _on_dm_recipient_add(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                dm_id = getattr(e, "dm_id", None)
                uid = getattr(e, "user_id", None)
                if dm_id and uid and dm_id in self._dms:
                    dm = self._dms[dm_id]
                    if uid not in dm.participant_ids:
                        dm.participant_ids.append(uid)
                self.dm_list_changed.emit()
            self._run_on_main.emit(_apply)

        @self.gateway.on("dm_recipient_remove")
        async def _on_dm_recipient_remove(event):  # noqa: ANN001
            def _apply(e=event):  # noqa: ANN001
                dm_id = getattr(e, "dm_id", None)
                uid = getattr(e, "user_id", None)
                if dm_id and uid and dm_id in self._dms:
                    dm = self._dms[dm_id]
                    if uid in dm.participant_ids:
                        dm.participant_ids.remove(uid)
                self.dm_list_changed.emit()
            self._run_on_main.emit(_apply)
