"""MemoryConsolidator for memory decay pruning and semantic consolidation."""

from __future__ import annotations

import time

from nexusai.brain.memory.indexer import IndexedMemoryItem, MemoryIndexer, MemoryType


class MemoryConsolidator:
    """Consolidates episodic memory items into permanent semantic knowledge entries and prunes stale items."""

    def consolidate_memories(
        self,
        indexer: MemoryIndexer,
        max_age_sec: float = 86400.0,
    ) -> IndexedMemoryItem | None:
        """Consolidate episodic memory items older than max_age_sec into a consolidated semantic summary."""
        episodic_items = indexer.get_by_type(MemoryType.EPISODIC)
        if not episodic_items:
            return None

        current_time = time.time()
        old_items = [i for i in episodic_items if current_time - i.timestamp > max_age_sec]

        if not old_items:
            return None

        consolidated_text = (
            f"[Consolidated Semantic Memory from {len(old_items)} episodic items]: "
            + "; ".join(i.text for i in old_items)
        )
        consolidated_item = IndexedMemoryItem(
            item_id=f"semantic-consolidated-{int(current_time)}",
            memory_type=MemoryType.SEMANTIC,
            text=consolidated_text,
            source="memory_consolidator",
            importance_score=0.9,
            timestamp=current_time,
        )

        indexer.index_item(consolidated_item)
        return consolidated_item
