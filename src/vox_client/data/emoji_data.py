"""Lazy-loaded Unicode emoji data from bundled emoji.json."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from vox_client._frozen import EMOJI_JSON

log = logging.getLogger(__name__)

CATEGORIES = ("People", "Nature", "Food", "Travel", "Activities", "Objects", "Symbols", "Flags")


@dataclass(frozen=True, slots=True)
class EmojiEntry:
    emoji: str
    name: str
    category: str


_entries: list[EmojiEntry] | None = None
_by_category: dict[str, list[EmojiEntry]] | None = None


def _load() -> None:
    global _entries, _by_category
    if _entries is not None:
        return
    raw = json.loads(EMOJI_JSON.read_text(encoding="utf-8"))
    _entries = [EmojiEntry(**e) for e in raw]
    _by_category = {}
    for entry in _entries:
        _by_category.setdefault(entry.category, []).append(entry)
    log.debug("Loaded %d emoji entries", len(_entries))


def all_entries() -> list[EmojiEntry]:
    _load()
    return _entries  # type: ignore[return-value]


def by_category() -> dict[str, list[EmojiEntry]]:
    _load()
    return _by_category  # type: ignore[return-value]


def search(query: str, limit: int = 25) -> list[EmojiEntry]:
    _load()
    assert _entries is not None
    q = query.lower()
    results: list[EmojiEntry] = []
    for entry in _entries:
        if q in entry.name:
            results.append(entry)
            if len(results) >= limit:
                break
    return results
