"""MemoryRetriever for fetching candidate memory items across multi-tier indices."""

from __future__ import annotations

from nexusai.brain.memory.indexer import IndexedMemoryItem, MemoryIndexer, MemoryType


class MemoryRetriever:
    """Retrieves candidate memory items matching query keywords, types, and importance thresholds."""

    def __init__(self, indexer: MemoryIndexer) -> None:
        self.indexer = indexer

    def retrieve_candidates(
        self,
        query: str = "",
        memory_types: tuple[MemoryType, ...] | None = None,
        min_importance: float = 0.0,
        max_results: int = 10,
    ) -> list[IndexedMemoryItem]:
        """Retrieve candidate memory items filtering by query, types, and importance."""
        all_items = self.indexer.get_all()
        candidates: list[IndexedMemoryItem] = []

        query_terms = set(query.lower().split()) if query else set()

        for item in all_items:
            if item.importance_score < min_importance:
                continue

            if memory_types and item.memory_type not in memory_types:
                continue

            if query_terms:
                item_text_lower = item.text.lower()
                if not any(term in item_text_lower for term in query_terms):
                    continue

            candidates.append(item)

        candidates.sort(key=lambda i: i.importance_score, reverse=True)
        return candidates[:max_results]
