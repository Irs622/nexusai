"""MemoryRetriever implementation providing recency and relevance scoring over IMemoryStore."""

from __future__ import annotations

import math
import time
from typing import Any

from nexusai.brain.domain.memory import MemoryEntry, MemoryQuery
from nexusai.brain.ports.memory_port import IMemoryRetriever, IMemoryStore
from nexusai.brain.ports.observability_port import IObservabilityPort


def compute_lexical_similarity(text_a: str, text_b: str) -> float:
    """Calculate normalized lexical overlap score between two text strings."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a.intersection(words_b)
    union = words_a.union(words_b)
    return len(intersection) / float(len(union))


class MemoryRetriever(IMemoryRetriever):
    """Hybrid memory retriever ranking results using recency decay and relevance scores."""

    def __init__(
        self,
        store: IMemoryStore,
        telemetry: IObservabilityPort | None = None,
    ) -> None:
        self.store = store
        self.telemetry = telemetry

    async def retrieve(self, query: MemoryQuery) -> list[MemoryEntry]:
        """Retrieve memory entries matching session_id with hybrid recency and relevance scoring."""
        all_memories: list[MemoryEntry] = []
        for m_type in query.memory_types:
            type_mems = await self.store.list_session_memories(query.session_id, memory_type=m_type)
            all_memories.extend(type_mems)

        now = time.time()
        scored_entries: list[tuple[float, MemoryEntry]] = []

        for entry in all_memories:
            # Enforce invalidation filtering invariant
            if entry.provenance.invalidated and not query.include_invalidated:
                continue

            # Calculate recency score (decay over 86,400s / 1 day)
            age_seconds = max(0.0, now - entry.created_at)
            recency_score = math.exp(-age_seconds / 86400.0)

            # Calculate relevance score
            relevance_score = compute_lexical_similarity(query.query_text, entry.content)

            hybrid_score = (recency_score * query.recency_weight) + (relevance_score * query.semantic_weight)

            if hybrid_score >= query.min_relevance:
                scored_entries.append((hybrid_score, entry))

        # Sort by hybrid score DESC
        scored_entries.sort(key=lambda item: item[0], reverse=True)

        return [item[1] for item in scored_entries[: query.top_k]]
