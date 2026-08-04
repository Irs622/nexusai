"""
StoreMemoryUseCase implementation.
"""

from __future__ import annotations

from typing import Callable
import uuid

from nexusai.memory.domain.content import MemoryContent
from nexusai.memory.domain.metadata import MemoryMetadata
from nexusai.memory.domain.record import MemoryRecord, MemoryScope, MemoryType
from nexusai.memory.uow.unit_of_work import MemoryUnitOfWork


class StoreMemoryUseCase:
    """Use case for transactionally storing a new MemoryRecord."""

    def __init__(
        self,
        uow: MemoryUnitOfWork,
        id_generator: Callable[[], str] | None = None,
    ) -> None:
        self._uow = uow
        self._id_generator = id_generator or (lambda: str(uuid.uuid4()))

    async def execute(
        self,
        raw_text: str,
        memory_type: MemoryType = MemoryType.EPISODIC,
        scope: MemoryScope = MemoryScope.SESSION,
        metadata: MemoryMetadata | None = None,
    ) -> MemoryRecord:
        """Execute store usecase within MemoryUnitOfWork transaction boundary."""
        record_id = self._id_generator()
        content = MemoryContent(raw_text=raw_text)
        record = MemoryRecord(
            id=record_id,
            memory_type=memory_type,
            scope=scope,
            metadata=metadata or MemoryMetadata(),
            content=content,
        )

        async with self._uow.transaction():
            await self._uow.records.add(record)

        return record
