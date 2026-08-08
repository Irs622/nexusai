"""
OutboxRecord and OutboxRepository contracts for transactional event outbox pattern.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class OutboxStatus(str, Enum):
    """Outbox record delivery status."""

    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    FAILED = "FAILED"


@dataclass
class OutboxRecord:
    """Outbox record entry stored inside database transaction."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    payload_bytes: bytes = b""
    created_at: float = field(default_factory=time.time)
    status: OutboxStatus = OutboxStatus.PENDING
    retry_count: int = 0
    error_message: str | None = None


class OutboxRepository(ABC):
    """Abstract contract for outbox record persistence."""

    @abstractmethod
    async def enqueue(self, record: OutboxRecord) -> None:
        """Enqueue an OutboxRecord within active database transaction."""
        pass

    @abstractmethod
    async def fetch_pending(self, limit: int = 100) -> Sequence[OutboxRecord]:
        """Fetch pending outbox records for background worker dispatch."""
        pass

    @abstractmethod
    async def mark_dispatched(self, record_id: str) -> None:
        """Mark outbox record as successfully dispatched to EventBus."""
        pass

    async def mark_published(self, record_id: str) -> None:
        """Alias for mark_dispatched."""
        await self.mark_dispatched(record_id)

    @abstractmethod
    async def mark_failed(self, record_id: str, error: str = "", error_message: str = "") -> None:
        """Mark outbox record as failed."""
        pass
