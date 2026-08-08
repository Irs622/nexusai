"""ContextCompressor and DeduplicatingClusterCompressor for summarizing and compressing memory context."""

from __future__ import annotations

from nexusai.brain.memory.ranker import RankedMemoryItem


class ContextCompressor:
    """Compresses candidate memory items to adhere to token budget limits."""

    def compress_memories(
        self,
        ranked_items: list[RankedMemoryItem],
        max_units: int = 32000,
    ) -> tuple[list[RankedMemoryItem], str]:
        """Compress ranked memory items into a compact context summary string."""
        retained: list[RankedMemoryItem] = []
        current_units = 0

        summary_lines = ["[Memory Context Summary]"]

        for item in ranked_items:
            estimated_units = max(1, len(item.item.text) // 4)
            if current_units + estimated_units > max_units:
                break

            retained.append(item)
            current_units += estimated_units
            summary_lines.append(f"- [{item.item.memory_type.value}] {item.item.text}")

        summary_text = "\n".join(summary_lines) if len(retained) > 0 else ""
        return retained, summary_text


class DeduplicatingClusterCompressor(ContextCompressor):
    """Deduplicates and clusters redundant memory items before compression."""

    def compress_memories(
        self,
        ranked_items: list[RankedMemoryItem],
        max_units: int = 32000,
    ) -> tuple[list[RankedMemoryItem], str]:
        """Deduplicate exact/near-duplicate texts and compress remaining items."""
        seen_texts: set[str] = set()
        deduped: list[RankedMemoryItem] = []

        for item in ranked_items:
            norm_text = item.item.text.strip().lower()
            if norm_text not in seen_texts:
                seen_texts.add(norm_text)
                deduped.append(item)

        return super().compress_memories(deduped, max_units=max_units)
