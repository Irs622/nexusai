"""
ForgetMemoryUseCase implementation.
"""

from __future__ import annotations

from nexusai.memory.uow.unit_of_work import MemoryUnitOfWork


class ForgetMemoryUseCase:
    """Use case for transactionally deleting a MemoryRecord by ID."""

    def __init__(self, uow: MemoryUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, record_id: str) -> bool:
        """Execute forget usecase."""
        async with self._uow.transaction():
            deleted = await self._uow.records.delete(record_id)
        return deleted
