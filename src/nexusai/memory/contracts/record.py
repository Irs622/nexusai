"""
Re-export domain record entities for contract compatibility.
"""

from __future__ import annotations

from nexusai.memory.domain.record import MemoryRecord, MemoryScope, MemoryType

__all__ = [
    "MemoryRecord",
    "MemoryScope",
    "MemoryType",
]
