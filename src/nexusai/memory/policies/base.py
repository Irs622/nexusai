"""
MemoryPolicy abstract base class and PolicyContext contracts.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from nexusai.memory.domain.record import MemoryRecord


@dataclass
class PolicyContext:
    """Evaluation context for MemoryPolicy execution."""

    records: list[MemoryRecord]
    current_time: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    retained_records: list[MemoryRecord] = field(default_factory=list)
    expired_records: list[MemoryRecord] = field(default_factory=list)


class MemoryPolicy(ABC):
    """Abstract contract for Memory governance policies."""

    @property
    def policy_name(self) -> str:
        """Return policy name."""
        return self.__class__.__name__

    @abstractmethod
    async def evaluate(self, context: PolicyContext) -> None:
        """Evaluate policy over records in-place within PolicyContext."""
        pass
