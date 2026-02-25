"""Global application state and gateway → Qt signal bridge."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import sys

from PyQt6.QtCore import QObject, QStandardPaths, QTimer, pyqtSignal

from vox_sdk import Client, GatewayClient
from vox_sdk.models.emoji import EmojiResponse
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
    voice_media_event = pyqtSignal(str, str)  # (event_type, detail) from media client
    speaking_changed = pyqtSignal(int, bool)  # (user_id, is_speaking)

    # Emoji signals
    emoji_changed = pyqtSignal()

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

    # -- voice ---------------------------------------------------------------

    def _log_missing_dlls(self) -> None:
        """Log which DLLs vox_media.pyd depends on and which are missing."""
        import os
        import ctypes
        try:
            import importlib.util
            spec = importlib.util.find_spec("vox_media")
            if spec is None or spec.submodule_search_locations is None:
                log.warning("  Cannot locate vox_media package for DLL diagnosis")
                return
            pkg_dir = spec.submodule_search_locations[0]
            log.info("  vox_media package dir: %s", pkg_dir)
            log.info("  Contents: %s", os.listdir(pkg_dir))
            # Check .libs dirs (delvewheel vendored DLLs)
            site_dir = os.path.dirname(pkg_dir)
            for libs_name in ("vox_media.libs", ".vox_media.libs"):
                libs_dir = os.path.join(site_dir, libs_name)
                if os.path.isdir(libs_dir):
                    log.info("  %s contents: %s", libs_name, os.listdir(libs_dir))
                else:
                    log.info("  %s directory NOT found", libs_name)
            # Try to identify the exact missing DLL using LoadLibraryEx
            pyd_files = [f for f in os.listdir(pkg_dir) if f.endswith(".pyd") and not f.startswith("__")]
            for pyd in pyd_files:
                pyd_path = os.path.join(pkg_dir, pyd)
                log.info("  Attempting LoadLibraryEx on %s ...", pyd)
                try:
                    ctypes.WinDLL(pyd_path)
                    log.info("    Loaded OK (unexpected)")
                except OSError as e:
                    log.warning("    LoadLibraryEx failed: %s", e)
                    # Use Windows API to get dependency info if available
                    try:
                        import subprocess
                        result = subprocess.run(
                            ["dumpbin", "/dependents", pyd_path],
                            capture_output=True, text=True, timeout=10,
                        )
                        if result.returncode == 0:
                            log.info("    DLL dependencies (dumpbin):\n%s", result.stdout)
                        else:
                            log.debug("    dumpbin not available")
                    except Exception:
                        log.debug("    dumpbin not available for dependency listing")
        except Exception:
            log.warning("  DLL diagnosis failed", exc_info=True)

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
                from PyQt6.QtCore import QSettings
                settings = QSettings("Vox", "VoxClient")
                input_vol = settings.value("av/input_volume", 100, type=int)
                output_vol = settings.value("av/output_volume", 100, type=int)
                gate = settings.value("av/noise_gate", 30, type=int)
                log.debug("AV settings: input=%d%% output=%d%% gate=%d%%",
                          input_vol, output_vol, gate)
                mc.set_input_volume(_log_volume(input_vol))
                mc.set_output_volume(_log_volume(output_vol))
                mc.set_noise_gate(gate / 100.0)
                log.info("Connecting media client to %s (room=%d, user=%d)",
                         resp.media_url, room_id, self.user_id)
                mc.connect(
                    url=resp.media_url,
                    token=resp.media_token,
                    room_id=room_id,
                    user_id=self.user_id,
                    cert_der=cert_der,
                )
                self._media_client = mc
                self._media_url = resp.media_url
                self._media_cert_der = cert_der
                self._start_media_poll()
                log.info("Media client connected and polling started")
            except ImportError:
                log.warning("vox_media native extension not available – audio disabled", exc_info=True)
                if sys.platform == "win32":
                    self._log_missing_dlls()
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
                            self._media_client.connect(
                                url=self._media_url,
                                token=token,
                                room_id=rid,
                                user_id=self.user_id,
                                cert_der=self._media_cert_der,
                            )
                            log.info("Media client reconnected with refreshed token")
                        else:
                            log.warning("media_token_refresh missing token or media_url "
                                        "(token=%s, url=%s)", bool(token), self._media_url)
                except Exception:
                    log.error("Failed to handle media_token_refresh", exc_info=True)
            self._run_on_main.emit(_apply)
