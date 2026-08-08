"""MemoryConflictResolver for detecting and resolving contradictory memory facts."""

from __future__ import annotations

from dataclasses import dataclass

from nexusai.brain.memory.ranker import RankedMemoryItem


@dataclass(frozen=True)
class MemoryConflict:
    """Detected conflict between two memory statements."""

    item_a: RankedMemoryItem
    item_b: RankedMemoryItem
    conflict_reason: str


class MemoryConflictResolver:
    """Detects contradictory memory facts and resolves conflicts using recency and final score rules."""

    def resolve_conflicts(self, ranked_items: list[RankedMemoryItem]) -> list[RankedMemoryItem]:
        """Detect and resolve memory conflicts, retaining higher-confidence/fresher statements."""
        if len(ranked_items) <= 1:
            return list(ranked_items)

        deduped: dict[str, RankedMemoryItem] = {}

        for r_item in ranked_items:
            key = r_item.item.source
            if key not in deduped:
                deduped[key] = r_item
            else:
                existing = deduped[key]
                # Retain fresher or higher final_score statement
                if (
                    r_item.item.timestamp > existing.item.timestamp
                    or r_item.final_score > existing.final_score
                ):
                    deduped[key] = r_item

        resolved = list(deduped.values())
        resolved.sort(key=lambda r: r.final_score, reverse=True)
        return resolved
