"""Centralized caches — in-memory LRU backed by disk persistence.

Usage:
    from vox_client.cache import media_cache, message_cache
    media_cache.put(url, data)
    data = media_cache.get(url)  # bytes | None

    message_cache.put("feed:1", messages, meta)
    result = message_cache.get("feed:1")  # (messages, meta) | None
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import OrderedDict
from dataclasses import dataclass, asdict
from pathlib import Path

from PySide6.QtCore import QStandardPaths

log = logging.getLogger(__name__)

# Defaults
_DEFAULT_MEM_MAX = 200  # max entries in memory
_DEFAULT_DISK_MAX_MB = 100  # max disk usage in MB


class MediaCache:
    """LRU cache with disk persistence under QStandardPaths.CacheLocation."""

    def __init__(
        self,
        subdir: str = "media",
        mem_max: int = _DEFAULT_MEM_MAX,
        disk_max_bytes: int = _DEFAULT_DISK_MAX_MB * 1024 * 1024,
    ) -> None:
        self._subdir = subdir
        self._mem_max = mem_max
        self._disk_max = disk_max_bytes
        self._mem: OrderedDict[str, bytes] = OrderedDict()
        self._disk_dir: Path | None = None

    def _get_dir(self) -> Path:
        if self._disk_dir is None:
            root = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.CacheLocation,
            )
            self._disk_dir = Path(root) / self._subdir
            self._disk_dir.mkdir(parents=True, exist_ok=True)
            log.debug("Cache dir: %s", self._disk_dir)
        return self._disk_dir

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()

    def get(self, url: str) -> bytes | None:
        """Look up by URL. Returns bytes or None. Promotes entry in LRU."""
        # In-memory hit
        if url in self._mem:
            self._mem.move_to_end(url)
            log.debug("MEM HIT %s (%d bytes)", url[:80], len(self._mem[url]))
            return self._mem[url]
        # Disk hit
        path = self._get_dir() / self._key(url)
        if path.exists():
            try:
                data = path.read_bytes()
                # Touch atime for disk LRU
                os.utime(path)
            except OSError:
                log.debug("DISK READ ERROR %s", url[:80], exc_info=True)
                return None
            log.debug("DISK HIT %s (%d bytes)", url[:80], len(data))
            self._mem_put(url, data)
            return data
        log.debug("MISS %s", url[:80])
        return None

    def put(self, url: str, data: bytes) -> None:
        """Store data for a URL in both memory and disk."""
        log.debug("PUT %s (%d bytes)", url[:80], len(data))
        self._mem_put(url, data)
        self._disk_put(url, data)

    def _mem_put(self, url: str, data: bytes) -> None:
        self._mem[url] = data
        self._mem.move_to_end(url)
        evicted = 0
        while len(self._mem) > self._mem_max:
            self._mem.popitem(last=False)
            evicted += 1
        if evicted:
            log.debug("MEM EVICT %d entries (size now %d)", evicted, len(self._mem))

    def _disk_put(self, url: str, data: bytes) -> None:
        try:
            path = self._get_dir() / self._key(url)
            path.write_bytes(data)
        except OSError:
            log.debug("DISK WRITE ERROR %s", url[:80], exc_info=True)
            return
        self._maybe_evict_disk()

    def _maybe_evict_disk(self) -> None:
        """Evict oldest-accessed files if total size exceeds the cap."""
        cache_dir = self._get_dir()
        try:
            files = [f for f in cache_dir.iterdir() if f.is_file()]
        except OSError:
            return
        total = sum(f.stat().st_size for f in files)
        if total <= self._disk_max:
            return
        log.debug("DISK EVICT starting: %d bytes > %d limit", total, self._disk_max)
        # Sort by access time, oldest first
        files.sort(key=lambda f: f.stat().st_atime)
        evicted = 0
        for f in files:
            if total <= self._disk_max:
                break
            try:
                size = f.stat().st_size
                f.unlink()
                total -= size
                evicted += 1
            except OSError:
                continue
        log.debug("DISK EVICT done: removed %d files, %d bytes remaining", evicted, total)

    def clear_memory(self) -> None:
        """Drop in-memory entries (disk untouched)."""
        log.debug("MEM CLEAR (%d entries dropped)", len(self._mem))
        self._mem.clear()


# Singleton instance used by media_widgets and anything else
media_cache = MediaCache()


# ---------------------------------------------------------------------------
# Message cache — per-channel message list with LRU + disk persistence
# ---------------------------------------------------------------------------

_MSG_MEM_MAX = 50   # max channels in memory
_MSG_DISK_MAX = 200  # max channels on disk


@dataclass
class ChannelMeta:
    """Pagination state for a cached channel."""

    oldest_msg_id: int | None = None
    newest_msg_id: int | None = None
    has_more: bool = True


class MessageCache:
    """LRU message cache keyed by ``"feed:{id}"`` or ``"dm:{id}"``."""

    def __init__(
        self,
        subdir: str = "messages",
        mem_max: int = _MSG_MEM_MAX,
        disk_max: int = _MSG_DISK_MAX,
    ) -> None:
        self._subdir = subdir
        self._mem_max = mem_max
        self._disk_max = disk_max
        self._mem: OrderedDict[str, list[dict]] = OrderedDict()
        self._meta: dict[str, ChannelMeta] = {}
        self._disk_dir: Path | None = None

    def _get_dir(self) -> Path:
        if self._disk_dir is None:
            root = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.CacheLocation,
            )
            self._disk_dir = Path(root) / self._subdir
            self._disk_dir.mkdir(parents=True, exist_ok=True)
            log.debug("Message cache dir: %s", self._disk_dir)
        return self._disk_dir

    @staticmethod
    def _disk_key(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest() + ".json"

    # -- public reads ----------------------------------------------------------

    def get(self, key: str) -> tuple[list[dict], ChannelMeta] | None:
        """Return ``(messages_as_dicts, meta)`` or ``None`` on miss.

        Callers should use ``MessageResponse.model_validate(d)`` to rehydrate.
        """
        if key in self._mem:
            self._mem.move_to_end(key)
            meta = self._meta.get(key, ChannelMeta())
            log.debug("MEM HIT %s (%d msgs)", key, len(self._mem[key]))
            return self._mem[key], meta

        path = self._get_dir() / self._disk_key(key)
        if path.exists():
            try:
                raw = json.loads(path.read_text("utf-8"))
                os.utime(path)
            except (OSError, json.JSONDecodeError):
                log.debug("MSG DISK READ ERROR %s", key, exc_info=True)
                return None
            messages = raw.get("messages", [])
            meta_raw = raw.get("meta", {})
            meta = ChannelMeta(
                oldest_msg_id=meta_raw.get("oldest_msg_id"),
                newest_msg_id=meta_raw.get("newest_msg_id"),
                has_more=meta_raw.get("has_more", True),
            )
            log.debug("DISK HIT %s (%d msgs)", key, len(messages))
            self._mem[key] = messages
            self._mem.move_to_end(key)
            self._meta[key] = meta
            self._evict_mem()
            return messages, meta

        log.debug("MISS %s", key)
        return None

    # -- public writes ---------------------------------------------------------

    def put(self, key: str, messages: list[dict], meta: ChannelMeta) -> None:
        """Store a full channel message list (as dicts) in chronological order."""
        log.debug("PUT %s (%d msgs)", key, len(messages))
        self._mem[key] = messages
        self._mem.move_to_end(key)
        self._meta[key] = meta
        self._evict_mem()
        self._disk_write(key)

    def append(self, key: str, msg_dict: dict) -> None:
        """Append a single new message (from gateway) to the end."""
        if key not in self._mem:
            return
        self._mem[key].append(msg_dict)
        self._mem.move_to_end(key)
        meta = self._meta.get(key, ChannelMeta())
        msg_id = msg_dict.get("msg_id")
        if msg_id is not None:
            meta.newest_msg_id = msg_id
        self._meta[key] = meta
        self._disk_write(key)

    def update(self, key: str, msg_id: int, body: str, edit_timestamp: int | None = None) -> None:
        """Update an existing message's body (and optionally edit_timestamp)."""
        if key not in self._mem:
            return
        for d in self._mem[key]:
            if d.get("msg_id") == msg_id:
                d["body"] = body
                if edit_timestamp is not None:
                    d["edit_timestamp"] = edit_timestamp
                break
        self._disk_write(key)

    def delete(self, key: str, msg_id: int) -> None:
        """Remove a message from the cache."""
        if key not in self._mem:
            return
        self._mem[key] = [d for d in self._mem[key] if d.get("msg_id") != msg_id]
        self._disk_write(key)

    def prepend(self, key: str, messages: list[dict], meta: ChannelMeta) -> None:
        """Prepend older messages (from pagination) to the front."""
        if key not in self._mem:
            return
        self._mem[key] = messages + self._mem[key]
        self._mem.move_to_end(key)
        self._meta[key] = meta
        self._disk_write(key)

    def clear_memory(self) -> None:
        """Drop in-memory entries (disk untouched)."""
        log.debug("MSG MEM CLEAR (%d entries dropped)", len(self._mem))
        self._mem.clear()
        self._meta.clear()

    # -- internal --------------------------------------------------------------

    def _evict_mem(self) -> None:
        evicted = 0
        while len(self._mem) > self._mem_max:
            evicted_key, _ = self._mem.popitem(last=False)
            self._meta.pop(evicted_key, None)
            evicted += 1
        if evicted:
            log.debug("MSG MEM EVICT %d entries (size now %d)", evicted, len(self._mem))

    def _disk_write(self, key: str) -> None:
        messages = self._mem.get(key)
        if messages is None:
            return
        meta = self._meta.get(key, ChannelMeta())
        payload = {"messages": messages, "meta": asdict(meta)}
        try:
            path = self._get_dir() / self._disk_key(key)
            path.write_text(json.dumps(payload), "utf-8")
        except OSError:
            log.debug("MSG DISK WRITE ERROR %s", key, exc_info=True)
            return
        self._evict_disk()

    def _evict_disk(self) -> None:
        cache_dir = self._get_dir()
        try:
            files = [f for f in cache_dir.iterdir() if f.is_file()]
        except OSError:
            return
        if len(files) <= self._disk_max:
            return
        log.debug("MSG DISK EVICT starting: %d files > %d limit", len(files), self._disk_max)
        files.sort(key=lambda f: f.stat().st_atime)
        evicted = 0
        for f in files:
            if len(files) - evicted <= self._disk_max:
                break
            try:
                f.unlink()
                evicted += 1
            except OSError:
                continue
        log.debug("MSG DISK EVICT done: removed %d files", evicted)


message_cache = MessageCache()
