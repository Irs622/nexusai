"""
MemorySerializer abstract base contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from nexusai.memory.domain.record import MemoryRecord


class MemorySerializer(ABC):
    """Abstract contract for serializing and deserializing MemoryRecord aggregate roots."""

    @abstractmethod
    def serialize(self, record: MemoryRecord) -> bytes:
        """Serialize a MemoryRecord into raw byte payload."""
        pass

    @abstractmethod
    def deserialize(self, payload_bytes: bytes) -> MemoryRecord:
        """Deserialize raw byte payload back into a MemoryRecord instance."""
        pass
