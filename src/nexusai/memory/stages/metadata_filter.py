"""
MetadataFilterStage implementation for filtering records by scope, owner, tags, and TTL.
"""

from __future__ import annotations

import time

from nexusai.memory.contracts.retrieval import RetrievalContext, RetrievalStage


class MetadataFilterStage(RetrievalStage):
    """RetrievalStage middleware filtering candidate records by metadata criteria."""

    def __init__(
        self,
        required_scope: str | None = None,
        required_owner: str | None = None,
        required_tags: list[str] | None = None,
        filter_expired_ttl: bool = True,
    ) -> None:
        self._scope = required_scope
        self._owner = required_owner
        self._tags = required_tags or []
        self._filter_ttl = filter_expired_ttl

    async def execute(self, context: RetrievalContext) -> None:
        """Filter context.candidate_records in-place."""
        now = time.time()
        filtered = []

        for record in context.candidate_records:
            meta = record.metadata

            # 1. Scope filter
            if self._scope and record.scope.value != self._scope:
                continue

            # 2. Owner filter
            if self._owner and meta.owner != self._owner:
                continue

            # 3. Tags filter
            if self._tags and not any(t in meta.tags for t in self._tags):
                continue

            # 4. TTL expiration filter
            if self._filter_ttl and meta.ttl_seconds is not None:
                if now > (meta.created_at + meta.ttl_seconds):
                    continue

            # 5. Archived filter
            if meta.archived:
                continue

            filtered.append(record)

        context.candidate_records = filtered
