"""
DeduplicationPolicy for identifying duplicate MemoryRecord content.
"""

from __future__ import annotations

import hashlib

from nexusai.memory.policies.base import MemoryPolicy, PolicyContext


class DeduplicationPolicy(MemoryPolicy):
    """MemoryPolicy identifying exact or fuzzy duplicate records."""

    def __init__(self, deduplicate_by_content_hash: bool = True) -> None:
        self._hash_dedup = deduplicate_by_content_hash

    async def evaluate(self, context: PolicyContext) -> None:
        """Filter out duplicate records."""
        seen_hashes: set[str] = set()
        retained = []
        duplicates = []

        for record in context.records:
            text = (record.content.raw_text or "").strip()
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

            if content_hash in seen_hashes:
                duplicates.append(record)
            else:
                seen_hashes.add(content_hash)
                retained.append(record)

        context.retained_records = retained
        context.expired_records.extend(duplicates)
        context.metadata["duplicates_removed_count"] = len(duplicates)
