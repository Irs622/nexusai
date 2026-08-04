"""
MemoryCommandService handling state mutation operations.
"""

from __future__ import annotations

from typing import Any

from nexusai.memory.contracts.storage import MemoryStorage
from nexusai.memory.domain.metadata import MemoryMetadata
from nexusai.memory.domain.record import MemoryRecord, MemoryScope, MemoryType
from nexusai.memory.metrics import MemoryMetricsCollector
from nexusai.memory.usecases.forget import ForgetMemoryUseCase
from nexusai.memory.usecases.store import StoreMemoryUseCase


class MemoryCommandService:
    """Service handling state mutation memory operations (store, forget, archive)."""

    def __init__(
        self,
        store_usecase: StoreMemoryUseCase,
        forget_usecase: ForgetMemoryUseCase,
        storage: MemoryStorage | None = None,
        metrics: MemoryMetricsCollector | None = None,
    ) -> None:
        self._store_usecase = store_usecase
        self._forget_usecase = forget_usecase
        self._storage = storage
        self._metrics = metrics or MemoryMetricsCollector()

    async def store(
        self,
        raw_text: str,
        memory_type: MemoryType = MemoryType.EPISODIC,
        scope: MemoryScope = MemoryScope.SESSION,
        metadata: MemoryMetadata | None = None,
    ) -> MemoryRecord:
        """Store new MemoryRecord."""
        self._metrics.increment_counter("store_count")
        return await self._store_usecase.execute(
            raw_text=raw_text, memory_type=memory_type, scope=scope, metadata=metadata
        )

    async def forget(self, record_id: str) -> bool:
        """Forget memory record by ID."""
        self._metrics.increment_counter("forget_count")
        return await self._forget_usecase.execute(record_id=record_id)

    async def archive(self, record_id: str, reason: str = "user_action") -> bool:
        """Archive memory record by ID."""
        if not self._storage:
            return False
        record = await self._storage.get(record_id)
        if not record:
            return False
        record.archive(reason=reason)
        await self._storage.save(record)
        return True
