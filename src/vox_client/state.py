"""Global application state and gateway → Qt signal bridge."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from vox_sdk import Client, GatewayClient
from vox_sdk.models.members import MemberResponse
from vox_sdk.models.roles import RoleResponse
from vox_sdk.models.server import FeedInfo, RoomInfo, CategoryInfo, ServerLayoutResponse
from vox_sdk.models.users import PresenceResponse
from vox_sdk.permissions import Permissions

from vox_client.theme import Theme, role_color_for_int


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

    # UI signals
    layout_loaded = pyqtSignal()
    layout_changed = pyqtSignal()
    theme_changed = pyqtSignal()

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
            return member.nickname or member.display_name or str(user_id)
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

        self.layout_loaded.emit()

    # -- gateway setup -------------------------------------------------------

    def set_gateway(self, gw: GatewayClient) -> None:
        self.gateway = gw
        self._register_handlers()

    def _register_handlers(self) -> None:
        assert self.gateway is not None

        @self.gateway.on("message_create")
        async def _on_message_create(event):  # noqa: ANN001
            self.message_received.emit(event)

        @self.gateway.on("message_update")
        async def _on_message_update(event):  # noqa: ANN001
            self.message_updated.emit(event)

        @self.gateway.on("message_delete")
        async def _on_message_delete(event):  # noqa: ANN001
            self.message_deleted.emit(event)

        @self.gateway.on("presence_update")
        async def _on_presence_update(event):  # noqa: ANN001
            uid = getattr(event, "user_id", None)
            if uid is not None:
                self._presences[uid] = PresenceResponse(
                    user_id=uid,
                    status=getattr(event, "status", "offline"),
                    custom_status=getattr(event, "custom_status", None),
                    activity=getattr(event, "activity", None),
                )
            self.presence_updated.emit(event)

        @self.gateway.on("typing_start")
        async def _on_typing_start(event):  # noqa: ANN001
            self.typing_started.emit(event)

        @self.gateway.on("member_join")
        async def _on_member_join(event):  # noqa: ANN001
            uid = getattr(event, "user_id", None)
            if uid is not None:
                self._members[uid] = MemberResponse(
                    user_id=uid,
                    display_name=getattr(event, "display_name", None),
                )
            self.member_joined.emit(event)

        @self.gateway.on("member_leave")
        async def _on_member_leave(event):  # noqa: ANN001
            uid = getattr(event, "user_id", None)
            if uid is not None:
                self._members.pop(uid, None)
                self._presences.pop(uid, None)
            self.member_left.emit(event)

        @self.gateway.on("member_update")
        async def _on_member_update(event):  # noqa: ANN001
            uid = getattr(event, "user_id", None)
            if uid is not None and uid in self._members:
                nick = getattr(event, "nickname", None)
                if nick is not None:
                    # Update in-place via reconstructing
                    old = self._members[uid]
                    self._members[uid] = MemberResponse(
                        user_id=old.user_id,
                        display_name=old.display_name,
                        avatar=old.avatar,
                        nickname=nick,
                        role_ids=old.role_ids,
                    )
            self.member_updated.emit(event)

        @self.gateway.on("role_assign")
        async def _on_role_assign(event):  # noqa: ANN001
            uid = getattr(event, "user_id", None)
            rid = getattr(event, "role_id", None)
            if uid and rid and uid in self._members:
                member = self._members[uid]
                if rid not in member.role_ids:
                    member.role_ids.append(rid)
            self.member_updated.emit(event)

        @self.gateway.on("role_revoke")
        async def _on_role_revoke(event):  # noqa: ANN001
            uid = getattr(event, "user_id", None)
            rid = getattr(event, "role_id", None)
            if uid and rid and uid in self._members:
                member = self._members[uid]
                if rid in member.role_ids:
                    member.role_ids.remove(rid)
            self.member_updated.emit(event)

        # -- Feed/Room/Category CRUD → layout_changed --------------------------

        @self.gateway.on("feed_create")
        async def _on_feed_create(event):  # noqa: ANN001
            feed = FeedInfo(
                feed_id=event.feed_id,
                name=event.name,
                type=event.type or "text",
                topic=getattr(event, "topic", None),
                category_id=getattr(event, "category_id", None),
            )
            self._feeds[feed.feed_id] = feed
            if self._layout is not None:
                self._layout.feeds.append(feed)
            self.layout_changed.emit()

        @self.gateway.on("feed_update")
        async def _on_feed_update(event):  # noqa: ANN001
            fid = event.feed_id
            if fid in self._feeds:
                old = self._feeds[fid]
                extra = getattr(event, "extra", {})
                self._feeds[fid] = old.model_copy(update=extra)
                if self._layout is not None:
                    self._layout.feeds = [
                        self._feeds[fid] if f.feed_id == fid else f
                        for f in self._layout.feeds
                    ]
            self.layout_changed.emit()

        @self.gateway.on("feed_delete")
        async def _on_feed_delete(event):  # noqa: ANN001
            fid = event.feed_id
            self._feeds.pop(fid, None)
            if self._layout is not None:
                self._layout.feeds = [f for f in self._layout.feeds if f.feed_id != fid]
            self.layout_changed.emit()

        @self.gateway.on("room_create")
        async def _on_room_create(event):  # noqa: ANN001
            room = RoomInfo(
                room_id=event.room_id,
                name=event.name,
                type=event.type or "voice",
                category_id=getattr(event, "category_id", None),
            )
            self._rooms[room.room_id] = room
            if self._layout is not None:
                self._layout.rooms.append(room)
            self.layout_changed.emit()

        @self.gateway.on("room_update")
        async def _on_room_update(event):  # noqa: ANN001
            rid = event.room_id
            if rid in self._rooms:
                old = self._rooms[rid]
                extra = getattr(event, "extra", {})
                self._rooms[rid] = old.model_copy(update=extra)
                if self._layout is not None:
                    self._layout.rooms = [
                        self._rooms[rid] if r.room_id == rid else r
                        for r in self._layout.rooms
                    ]
            self.layout_changed.emit()

        @self.gateway.on("room_delete")
        async def _on_room_delete(event):  # noqa: ANN001
            rid = event.room_id
            self._rooms.pop(rid, None)
            if self._layout is not None:
                self._layout.rooms = [r for r in self._layout.rooms if r.room_id != rid]
            self.layout_changed.emit()

        @self.gateway.on("category_create")
        async def _on_category_create(event):  # noqa: ANN001
            cat = CategoryInfo(
                category_id=event.category_id,
                name=event.name,
                position=getattr(event, "position", 0) or 0,
            )
            self._categories[cat.category_id] = cat
            if self._layout is not None:
                self._layout.categories.append(cat)
            self.layout_changed.emit()

        @self.gateway.on("category_update")
        async def _on_category_update(event):  # noqa: ANN001
            cid = event.category_id
            if cid in self._categories:
                old = self._categories[cid]
                extra = getattr(event, "extra", {})
                self._categories[cid] = old.model_copy(update=extra)
                if self._layout is not None:
                    self._layout.categories = [
                        self._categories[cid] if ct.category_id == cid else ct
                        for ct in self._layout.categories
                    ]
            self.layout_changed.emit()

        @self.gateway.on("category_delete")
        async def _on_category_delete(event):  # noqa: ANN001
            cid = event.category_id
            self._categories.pop(cid, None)
            if self._layout is not None:
                self._layout.categories = [
                    ct for ct in self._layout.categories if ct.category_id != cid
                ]
            self.layout_changed.emit()
