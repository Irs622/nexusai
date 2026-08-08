"""MemoryIndexer for categorizing and indexing agent memories."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class MemoryType(str, Enum):
    """Classification type for indexed memories."""

    WORKING = "WORKING"
    EPISODIC = "EPISODIC"
    SEMANTIC = "SEMANTIC"
    PROCEDURAL = "PROCEDURAL"


@dataclass(frozen=True)
class IndexedMemoryItem:
    """Indexed memory entry container.

    Attributes:
        item_id: Unique memory UUID string.
        memory_type: MemoryType classification.
        text: Raw text content string.
        source: Origin source identifier (e.g. "observation:obs-1", "user_input").
        importance_score: Calculated importance score (0.0 to 1.0).
        timestamp: Epoch timestamp float when recorded.
        metadata: Metadata key-value dictionary.
    """

    item_id: str
    memory_type: MemoryType
    text: str
    source: str = "observation"
    importance_score: float = 0.5
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, str] = field(default_factory=dict)


class MemoryIndexer:
    """Categorizes and indexes memories across working, episodic, semantic, and procedural types."""

    def __init__(self) -> None:
        self._index: dict[MemoryType, list[IndexedMemoryItem]] = {t: [] for t in MemoryType}

    def index_item(self, item: IndexedMemoryItem) -> None:
        """Add an IndexedMemoryItem to the multi-tier index."""
        self._index[item.memory_type].append(item)

    def get_by_type(self, memory_type: MemoryType) -> list[IndexedMemoryItem]:
        """Fetch indexed items matching memory_type."""
        return list(self._index.get(memory_type, []))

    def get_all(self) -> list[IndexedMemoryItem]:
        """Fetch all indexed memory items across all types."""
        all_items: list[IndexedMemoryItem] = []
        for items in self._index.values():
            all_items.extend(items)
        return sorted(all_items, key=lambda i: i.timestamp, reverse=True)
