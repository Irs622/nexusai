"""
MemoryRecordRepository abstract contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from nexusai.memory.domain.record import MemoryRecord


class MemoryRecordRepository(ABC):
    """Abstract repository interface for MemoryRecord aggregate roots."""

    @abstractmethod
    async def add(self, record: MemoryRecord) -> None:
        """Add a new MemoryRecord."""
        pass

    @abstractmethod
    async def get_by_id(self, record_id: str) -> MemoryRecord | None:
        """Find a MemoryRecord by ID."""
        pass

    @abstractmethod
    async def delete(self, record_id: str) -> bool:
        """Delete a MemoryRecord by ID."""
        pass

    @abstractmethod
    async def list_all(self, limit: int = 100) -> Sequence[MemoryRecord]:
        """List all MemoryRecords up to limit."""
        pass
