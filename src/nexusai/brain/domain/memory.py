"""Domain models for Agent Context and Memory Lifecycle, Memory Provenance, and Privacy Boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Mapping

from nexusai.brain.domain.observability import sanitize_attributes


class MemoryType(str, Enum):
    """Tiered taxonomy for agent memory types."""

    WORKING = "working"      # Short-term execution buffer
    EPISODIC = "episodic"    # Historical execution trajectories
    SEMANTIC = "semantic"    # Long-term knowledge & facts


class PrivacyLevel(str, Enum):
    """Privacy boundary classification for memory entries."""

    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"  # Requires mandatory PII & secret redaction


@dataclass(frozen=True)
class MemoryProvenance:
    """Immutable provenance metadata tracking origin, confidence, and invalidation status."""

    source_type: str  # e.g., "user_input", "tool_output", "agent_reasoning", "system_prompt"
    source_id: str | None = None
    confidence: float = 1.0
    version: int = 1
    invalidated: bool = False


@dataclass(frozen=True)
class MemoryEntry:
    """Immutable domain representation of an agent memory item."""

    memory_id: str
    session_id: str
    execution_id: str | None
    memory_type: MemoryType
    content: str
    provenance: MemoryProvenance
    privacy_level: PrivacyLevel = PrivacyLevel.INTERNAL
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None  # TTL timestamp (None = durable until invalidated)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Enforce attribute secret sanitization at post-init
        sanitized = sanitize_attributes(self.metadata)
        object.__setattr__(self, "metadata", sanitized)


@dataclass(frozen=True)
class MemoryQuery:
    """Query parameters for memory retrieval and hybrid ranking."""

    session_id: str
    query_text: str
    memory_types: frozenset[MemoryType] = field(
        default_factory=lambda: frozenset({MemoryType.WORKING, MemoryType.EPISODIC, MemoryType.SEMANTIC})
    )
    top_k: int = 5
    min_relevance: float = 0.6
    recency_weight: float = 0.3
    semantic_weight: float = 0.7
    include_invalidated: bool = False
