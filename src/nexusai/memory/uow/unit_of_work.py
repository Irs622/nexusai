"""
Transactional MemoryUnitOfWork managing repository transaction lifecycle.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Sequence

from nexusai.kernel.outbox.repository import OutboxRecord, OutboxRepository, OutboxStatus
from nexusai.kernel.transaction import AsyncTransaction, UnitOfWork
from nexusai.memory.contracts.vector import VectorMatch
from nexusai.memory.domain.record import MemoryRecord
from nexusai.memory.repository.record_repo import MemoryRecordRepository
from nexusai.memory.repository.vector_repo import VectorRepository


class MemoryUnitOfWork(UnitOfWork):
    """Abstract Unit of Work managing transactional Memory repositories."""

    @property
    @abstractmethod
    def records(self) -> MemoryRecordRepository:
        """Return MemoryRecordRepository instance."""
        pass

    @property
    @abstractmethod
    def vector(self) -> VectorRepository:
        """Return VectorRepository instance."""
        pass

    @property
    @abstractmethod
    def outbox(self) -> OutboxRepository:
        """Return OutboxRepository instance."""
        pass

    @abstractmethod
    def transaction(self) -> AsyncTransaction:
        """Return an AsyncTransaction context manager instance."""
        pass


class InMemoryRecordRepository(MemoryRecordRepository):
    """In-memory implementation of MemoryRecordRepository."""

    def __init__(self) -> None:
        self._store: dict[str, MemoryRecord] = {}

    async def add(self, record: MemoryRecord) -> None:
        self._store[record.id] = record

    async def get_by_id(self, record_id: str) -> MemoryRecord | None:
        return self._store.get(record_id)

    async def get(self, record_id: str) -> MemoryRecord | None:
        return await self.get_by_id(record_id)

    async def update(self, record: MemoryRecord) -> None:
        await self.add(record)

    async def delete(self, record_id: str) -> bool:
        if record_id in self._store:
            del self._store[record_id]
            return True
        return False

    async def list_all(self, limit: int = 100) -> Sequence[MemoryRecord]:
        return list(self._store.values())[:limit]


class InMemoryVectorRepository(VectorRepository):
    """In-memory implementation of VectorRepository."""

    def __init__(self) -> None:
        self._vectors: dict[str, Sequence[float]] = {}

    async def upsert_vector(
        self, embedding_id: str, vector: Sequence[float], metadata: dict[str, str] | None = None
    ) -> None:
        self._vectors[embedding_id] = vector

    async def delete_vector(self, embedding_id: str) -> bool:
        if embedding_id in self._vectors:
            del self._vectors[embedding_id]
            return True
        return False

    async def search(self, query_vector: Sequence[float], top_k: int = 5) -> Sequence[VectorMatch]:
        results = []
        for eid in list(self._vectors.keys())[:top_k]:
            results.append(VectorMatch(record_id=eid, distance=0.1, similarity=0.9, metadata={}))
        return results


class InMemoryOutboxRepository(OutboxRepository):
    """In-memory implementation of OutboxRepository."""

    def __init__(self) -> None:
        self._records: list[OutboxRecord] = []

    async def enqueue(self, record: OutboxRecord) -> None:
        self._records.append(record)

    async def fetch_pending(self, limit: int = 100) -> Sequence[OutboxRecord]:
        return [r for r in self._records if r.status == OutboxStatus.PENDING][:limit]

    async def mark_dispatched(self, record_id: str) -> None:
        for r in self._records:
            if r.id == record_id:
                r.status = OutboxStatus.DISPATCHED

    async def mark_failed(self, record_id: str, error: str = "", error_message: str = "") -> None:
        err_str = error_message or error
        for r in self._records:
            if r.id == record_id:
                r.status = OutboxStatus.FAILED
                r.error_message = err_str


class DefaultMemoryUnitOfWork(MemoryUnitOfWork):
    """Default in-memory Unit of Work implementation for Memory Engine."""

    def __init__(
        self,
        records: MemoryRecordRepository | None = None,
        vector: VectorRepository | None = None,
        outbox: OutboxRepository | None = None,
    ) -> None:
        self._records = records or InMemoryRecordRepository()
        self._vector = vector or InMemoryVectorRepository()
        self._outbox = outbox or InMemoryOutboxRepository()

    @property
    def records(self) -> MemoryRecordRepository:
        return self._records

    @property
    def vector(self) -> VectorRepository:
        return self._vector

    @property
    def outbox(self) -> OutboxRepository:
        return self._outbox

    def transaction(self) -> AsyncTransaction:
        from nexusai.kernel.transaction import DefaultAsyncTransaction

        return DefaultAsyncTransaction()
