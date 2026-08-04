"""
Generic versioned OutboxSerializer interface and JSON implementation for domain event serialization.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import time
from typing import Any


class OutboxSerializer(ABC):
    """Abstract generic event serializer for Outbox records."""

    @abstractmethod
    def serialize(self, event: Any, event_type: str = "DomainEvent") -> bytes:
        """Serialize a domain event into versioned raw byte payload."""
        pass

    @abstractmethod
    def deserialize(self, payload_bytes: bytes) -> dict[str, Any]:
        """Deserialize versioned byte payload back into event payload dict."""
        pass


class JSONOutboxSerializer(OutboxSerializer):
    """JSON implementation of versioned OutboxSerializer."""

    def __init__(self, schema_version: str = "1.0.0") -> None:
        self._schema_version = schema_version

    def serialize(self, event: Any, event_type: str = "DomainEvent") -> bytes:
        """Serialize event with metadata envelope to JSON bytes."""
        if hasattr(event, "model_dump"):
            payload = event.model_dump()
        elif hasattr(event, "__dict__"):
            payload = event.__dict__
        elif isinstance(event, dict):
            payload = event
        else:
            payload = {"data": str(event)}

        envelope = {
            "schema_version": self._schema_version,
            "event_type": event_type,
            "created_at": time.time(),
            "payload": payload,
        }

        return json.dumps(envelope).encode("utf-8")

    def deserialize(self, payload_bytes: bytes) -> dict[str, Any]:
        """Deserialize versioned JSON bytes to envelope dict."""
        raw_str = payload_bytes.decode("utf-8")
        data = json.loads(raw_str)
        if isinstance(data, dict) and "payload" in data:
            return data
        return {
            "schema_version": self._schema_version,
            "event_type": "UnknownEvent",
            "created_at": time.time(),
            "payload": data if isinstance(data, dict) else {"data": data},
        }
