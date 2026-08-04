"""
RetrieveMemoryUseCase implementation.
"""

from __future__ import annotations

from nexusai.memory.domain.record import MemoryRecord
from nexusai.memory.uow.unit_of_work import MemoryUnitOfWork


class RetrieveMemoryUseCase:
    """Use case for retrieving a MemoryRecord by ID."""

    def __init__(self, uow: MemoryUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, record_id: str) -> MemoryRecord | None:
        """Execute retrieve usecase."""
        return await self._uow.records.get_by_id(record_id)
