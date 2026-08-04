"""
MemoryRecord DDD Aggregate Root enforcing domain invariants and event tracking.
"""

from __future__ import annotations

from enum import Enum
import time
import uuid
from typing import Any
from pydantic import BaseModel, Field, PrivateAttr

from nexusai.memory.domain.content import MemoryContent
from nexusai.memory.domain.metadata import MemoryMetadata


class MemoryType(str, Enum):
    """Memory record type classification."""

    EPISODIC = "EPISODIC"
    SEMANTIC = "SEMANTIC"
    PROCEDURAL = "PROCEDURAL"
    WORKING = "WORKING"


class MemoryScope(str, Enum):
    """Memory record target scope."""

    GLOBAL = "GLOBAL"
    SESSION = "SESSION"
    USER = "USER"


class MemoryRecord(BaseModel):
    """DDD Aggregate Root for memory records enforcing domain invariants."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    memory_type: MemoryType = Field(default=MemoryType.EPISODIC)
    scope: MemoryScope = Field(default=MemoryScope.SESSION)
    metadata: MemoryMetadata = Field(default_factory=MemoryMetadata)
    content: MemoryContent
    schema_version: str = Field(default="1.0.0")

    _domain_events: list[Any] = PrivateAttr(default_factory=list)

    model_config = {
        "arbitrary_types_allowed": True,
    }

    def touch(self, timestamp: float | None = None) -> None:
        """Domain invariant: update updated_at timestamp when modified."""
        new_ts = timestamp or time.time()
        updated_meta = self.metadata.model_dump()
        updated_meta["updated_at"] = new_ts
        object.__setattr__(self, "metadata", MemoryMetadata(**updated_meta))

    def archive(self) -> None:
        """Domain invariant: mark memory record as archived."""
        updated_meta = self.metadata.model_dump()
        updated_meta["archived"] = True
        updated_meta["updated_at"] = time.time()
        object.__setattr__(self, "metadata", MemoryMetadata(**updated_meta))

    def attach_embedding(self, embedding_id: str) -> None:
        """Domain invariant: attach vector store embedding reference ID."""
        updated_content = self.content.model_dump()
        updated_content["embedding_id"] = embedding_id
        object.__setattr__(self, "content", MemoryContent(**updated_content))

    def update_summary(self, summary: str) -> None:
        """Domain invariant: set compacted summary text."""
        updated_content = self.content.model_dump()
        updated_content["summary"] = summary
        object.__setattr__(self, "content", MemoryContent(**updated_content))

    def record_domain_event(self, event: Any) -> None:
        """Register a domain event raised by aggregate root methods."""
        self._domain_events.append(event)

    def pull_events(self) -> list[Any]:
        """Pull and flush domain events raised by aggregate root."""
        events = list(self._domain_events)
        self._domain_events.clear()
        return events
