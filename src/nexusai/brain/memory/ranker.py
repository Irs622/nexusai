"""MemoryRanker for multi-factor relevance, recency decay, confidence certainty, and quality scoring."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from nexusai.brain.memory.indexer import IndexedMemoryItem


@dataclass(frozen=True)
class RankedMemoryItem:
    """Ranked memory entry with multi-factor score breakdown."""

    item: IndexedMemoryItem
    relevance_score: float
    recency_score: float
    confidence_score: float
    final_score: float


class MemoryRanker:
    """Ranks candidate memory items using relevance, recency exponential decay, confidence certainty, and importance."""

    def __init__(self, half_life_sec: float = 3600.0) -> None:
        self.half_life_sec = half_life_sec

    def rank_memories(
        self,
        query: str,
        candidates: list[IndexedMemoryItem],
        now: float | None = None,
    ) -> list[RankedMemoryItem]:
        """Calculate final composite score: 0.40*relevance + 0.25*recency + 0.20*confidence + 0.15*importance."""
        current_time = now or time.time()
        query_words = set(query.lower().split()) if query else set()

        ranked: list[RankedMemoryItem] = []

        for item in candidates:
            # 1. Relevance score
            if query_words:
                match_count = sum(1 for w in query_words if w in item.text.lower())
                rel_score = min(1.0, match_count / max(1, len(query_words)))
            else:
                rel_score = 0.5

            # 2. Recency score (exponential decay)
            age = max(0.0, current_time - item.timestamp)
            rec_score = math.exp(-age / self.half_life_sec)

            # 3. Confidence score (certainty provenance)
            conf_score = item.importance_score

            # 4. Final composite score
            final = (
                (0.40 * rel_score)
                + (0.25 * rec_score)
                + (0.20 * conf_score)
                + (0.15 * item.importance_score)
            )

            ranked.append(
                RankedMemoryItem(
                    item=item,
                    relevance_score=round(rel_score, 3),
                    recency_score=round(rec_score, 3),
                    confidence_score=round(conf_score, 3),
                    final_score=round(final, 3),
                )
            )

        ranked.sort(key=lambda r: r.final_score, reverse=True)
        return ranked
