"""
DomainEvent and IntegrationEvent contracts for clean event classification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any
import uuid


@dataclass(frozen=True)
class EventHeader:
    """Standardized event header envelope metadata."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = "BaseEvent"
    schema_version: str = "1.0.0"
    created_at: float = field(default_factory=time.time)
    correlation_id: str | None = None


class BaseEvent:
    """Base event contract."""

    def __init__(self, event_type: str, payload: dict[str, Any], correlation_id: str | None = None) -> None:
        self.header = EventHeader(event_type=event_type, correlation_id=correlation_id)
        self.payload = payload


class DomainEvent(BaseEvent):
    """DomainEvent representing a state change in the core domain aggregate."""

    pass


class IntegrationEvent(BaseEvent):
    """IntegrationEvent representing an infrastructure or cross-system lifecycle notification."""

    pass


# Domain Event Definitions
class MemoryStoredEvent(DomainEvent):
    def __init__(self, record_id: str, scope: str, memory_type: str) -> None:
        super().__init__(
            event_type="MemoryStoredEvent",
            payload={"record_id": record_id, "scope": scope, "memory_type": memory_type},
        )


class MemoryArchivedEvent(DomainEvent):
    def __init__(self, record_id: str, reason: str = "user_action") -> None:
        super().__init__(
            event_type="MemoryArchivedEvent",
            payload={"record_id": record_id, "reason": reason},
        )


class MemoryExpiredEvent(DomainEvent):
    def __init__(self, record_id: str, ttl_seconds: float) -> None:
        super().__init__(
            event_type="MemoryExpiredEvent",
            payload={"record_id": record_id, "ttl_seconds": ttl_seconds},
        )


# Integration Event Definitions
class EmbeddingCompletedEvent(IntegrationEvent):
    def __init__(self, record_id: str, dimensions: int) -> None:
        super().__init__(
            event_type="EmbeddingCompletedEvent",
            payload={"record_id": record_id, "dimensions": dimensions},
        )


class VectorIndexedEvent(IntegrationEvent):
    def __init__(self, record_id: str, namespace: str) -> None:
        super().__init__(
            event_type="VectorIndexedEvent",
            payload={"record_id": record_id, "namespace": namespace},
        )


class PolicyAppliedEvent(IntegrationEvent):
    def __init__(self, policy_name: str, affected_records_count: int) -> None:
        super().__init__(
            event_type="PolicyAppliedEvent",
            payload={"policy_name": policy_name, "affected_records_count": affected_records_count},
        )
