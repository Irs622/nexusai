"""
InMemoryMemoryStore implementation.
"""

from __future__ import annotations

from typing import Sequence

from nexusai.memory.contracts.storage import MemoryStorage
from nexusai.memory.domain.record import MemoryRecord


class InMemoryMemoryStore(MemoryStorage):
    """Zero-overhead in-memory storage engine implementation."""

    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}

    async def save(self, record: MemoryRecord) -> None:
        """Save MemoryRecord into memory dictionary."""
        self._records[record.id] = record

    async def get(self, record_id: str) -> MemoryRecord | None:
        """Get MemoryRecord from memory dictionary."""
        return self._records.get(record_id)

    async def delete(self, record_id: str) -> bool:
        """Delete MemoryRecord from memory dictionary."""
        if record_id in self._records:
            del self._records[record_id]
            return True
        return False

    async def list_records(self, limit: int = 100) -> Sequence[MemoryRecord]:
        """List stored MemoryRecords up to limit."""
        return list(self._records.values())[:limit]
