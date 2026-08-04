"""
PolicyEngine for evaluating registered MemoryPolicy instances.
"""

from __future__ import annotations

from typing import Sequence

from nexusai.memory.domain.record import MemoryRecord
from nexusai.memory.policies.base import MemoryPolicy, PolicyContext


class PolicyEngine:
    """Evaluator engine running registered MemoryPolicy rules over records."""

    def __init__(self, policies: Sequence[MemoryPolicy] | None = None) -> None:
        self._policies: list[MemoryPolicy] = list(policies or [])

    def add_policy(self, policy: MemoryPolicy) -> None:
        """Register a new MemoryPolicy."""
        self._policies.append(policy)

    async def evaluate_policies(self, records: Sequence[MemoryRecord]) -> PolicyContext:
        """Run registered policies over candidate records."""
        context = PolicyContext(records=list(records))
        for policy in self._policies:
            await policy.evaluate(context)
        return context
