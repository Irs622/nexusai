"""
MemoryStorage abstract contract for persistent record storage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from nexusai.memory.contracts.record import MemoryRecord


class MemoryStorage(ABC):
    """Abstract contract for persistent memory record storage engines."""

    @abstractmethod
    async def save(self, record: MemoryRecord) -> None:
        """Save a MemoryRecord to storage."""
        pass

    @abstractmethod
    async def get(self, record_id: str) -> MemoryRecord | None:
        """Retrieve a MemoryRecord by ID."""
        pass

    @abstractmethod
    async def delete(self, record_id: str) -> bool:
        """Delete a MemoryRecord by ID."""
        pass

    @abstractmethod
    async def list_records(self, limit: int = 100) -> Sequence[MemoryRecord]:
        """List stored MemoryRecords up to limit."""
        pass
