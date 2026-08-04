"""
RetentionPolicy implementation for evaluating TTL expiration and record retention limits.
"""

from __future__ import annotations

from nexusai.memory.policies.base import MemoryPolicy, PolicyContext


class RetentionPolicy(MemoryPolicy):
    """MemoryPolicy evaluating TTL expiration and record retention limits."""

    def __init__(self, default_max_age_days: float = 30.0) -> None:
        self._max_age_seconds = default_max_age_days * 86400.0

    async def evaluate(self, context: PolicyContext) -> None:
        """Evaluate retention rules over context records."""
        now = context.current_time
        retained = []
        expired = []

        for record in context.records:
            meta = record.metadata

            # 1. TTL Check
            if meta.ttl_seconds is not None:
                if now > (meta.created_at + meta.ttl_seconds):
                    expired.append(record)
                    continue

            # 2. Max Retention Age Check
            age = now - meta.created_at
            if age > self._max_age_seconds:
                expired.append(record)
                continue

            retained.append(record)

        context.retained_records = retained
        context.expired_records = expired
