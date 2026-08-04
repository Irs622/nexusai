"""
JSONMemorySerializer implementation of MemorySerializer interface.
"""

from __future__ import annotations

import json

from nexusai.memory.domain.record import MemoryRecord
from nexusai.memory.serializer.base import MemorySerializer


class JSONMemorySerializer(MemorySerializer):
    """JSON implementation of MemorySerializer."""

    def serialize(self, record: MemoryRecord) -> bytes:
        """Serialize MemoryRecord aggregate to JSON bytes."""
        data = record.model_dump()
        return json.dumps(data).encode("utf-8")

    def deserialize(self, payload_bytes: bytes) -> MemoryRecord:
        """Deserialize JSON bytes to MemoryRecord aggregate."""
        raw_str = payload_bytes.decode("utf-8")
        data = json.loads(raw_str)
        return MemoryRecord(**data)
