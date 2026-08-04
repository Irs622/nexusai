"""
Transactional MemoryUnitOfWork managing repository transaction lifecycle.
"""

from __future__ import annotations

from abc import abstractmethod

from nexusai.kernel.outbox.repository import OutboxRepository
from nexusai.kernel.transaction import AsyncTransaction, UnitOfWork
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
