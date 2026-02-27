"""Centralized media cache — in-memory LRU backed by disk persistence.

Usage:
    from vox_client.cache import media_cache
    media_cache.put(url, data)
    data = media_cache.get(url)  # bytes | None
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections import OrderedDict
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
