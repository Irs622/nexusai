"""
IOutboxWriter port interface and JSON OutboxRecord contract.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from nexusai.brain.domain.version import SchemaVersion


@dataclass(frozen=True)
class OutboxRecord:
    """Immutable transactional outbox record container.

    Uses strict JSON contract serialization (never pickle or raw objects) for idempotency
    and cross-subsystem transport.

    Attributes:
        event_id: Unique UUID identifier for the outbox event (idempotency key).
        execution_id: Target turn execution UUID context.
        event_type: Domain event discriminator name (e.g. 'BrainTurnCompletedEvent').
        payload_json: Serialized JSON payload string.
        schema_version: Schema contract version.
        timestamp: UTC creation timestamp.
    """

    event_id: UUID = field(default_factory=uuid4)
    execution_id: UUID = field(default_factory=uuid4)
    event_type: str = "BrainTurnCompletedEvent"
    payload_json: str = "{}"
    schema_version: SchemaVersion = field(default_factory=SchemaVersion)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(
        cls,
        event_type: str,
        execution_id: UUID,
        payload: dict[str, Any],
        event_id: UUID | None = None,
    ) -> OutboxRecord:
        """Create an OutboxRecord with explicit JSON payload serialization.

        Args:
            event_type: Event type discriminator.
            execution_id: Execution context UUID.
            payload: Dictionary payload to serialize as JSON.
            event_id: Optional explicit event UUID (idempotency key).

        Returns:
            An immutable OutboxRecord.
        """
        return cls(
            event_id=event_id or uuid4(),
            execution_id=execution_id,
            event_type=event_type,
            payload_json=json.dumps(payload, default=str),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize OutboxRecord to dictionary format."""
        return {
            "event_id": str(self.event_id),
            "execution_id": str(self.execution_id),
            "event_type": self.event_type,
            "payload_json": self.payload_json,
            "schema_version": self.schema_version.to_dict(),
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutboxRecord:
        """Deserialize OutboxRecord from dictionary format."""
        version_data = data.get("schema_version", {})
        schema_version = (
            SchemaVersion.from_dict(version_data) if isinstance(version_data, dict) else SchemaVersion()
        )
        ts_val = data.get("timestamp")
        timestamp = datetime.fromisoformat(ts_val) if isinstance(ts_val, str) else datetime.now(timezone.utc)

        return cls(
            event_id=UUID(data["event_id"]) if "event_id" in data else uuid4(),
            execution_id=UUID(data["execution_id"]) if "execution_id" in data else uuid4(),
            event_type=str(data.get("event_type", "BrainTurnCompletedEvent")),
            payload_json=str(data.get("payload_json", "{}")),
            schema_version=schema_version,
            timestamp=timestamp,
        )


class IOutboxWriter(ABC):
    """Abstract port interface for writing transactional outbox records."""

    @abstractmethod
    async def write_record(self, record: OutboxRecord) -> bool:
        """Transactionally write an OutboxRecord.

        Args:
            record: OutboxRecord to persist.

        Returns:
            True if transaction committed successfully.
        """
        ...
