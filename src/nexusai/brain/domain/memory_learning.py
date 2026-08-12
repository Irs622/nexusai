"""Domain models, candidate taxonomy, decisions, and fingerprinting for Agent Memory Integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Mapping

from nexusai.brain.domain.memory import MemoryType, PrivacyLevel
from nexusai.brain.domain.observability import sanitize_attributes


class MemoryPromotionDecision(str, Enum):
    """Lifecycle decision for candidate memory learning items."""

    STORE_EPISODIC = "STORE_EPISODIC"
    PROMOTE_SEMANTIC = "PROMOTE_SEMANTIC"
    DISCARD = "DISCARD"
    INVALIDATE_EXISTING = "INVALIDATE_EXISTING"


@dataclass(frozen=True)
class MemoryCandidate:
    """Immutable domain representation of a candidate learned memory item."""

    content: str
    memory_type: MemoryType
    confidence: float
    source_type: str
    source_id: str
    session_id: str
    execution_id: str | None = None
    privacy_level: PrivacyLevel = PrivacyLevel.INTERNAL
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate candidate domain invariants and sanitize secret metadata."""
        if not self.content.strip():
            raise ValueError("content cannot be empty")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0 (got {self.confidence})")
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if not self.source_type.strip():
            raise ValueError("source_type cannot be empty")

        # Secret redaction invariant (P3-5-INV-02)
        sanitized = sanitize_attributes(self.metadata)
        object.__setattr__(self, "metadata", sanitized)


@dataclass(frozen=True)
class MemoryExtractionResult:
    """Immutable output container returned from IMemoryExtractor."""

    candidates: tuple[MemoryCandidate, ...]
    discarded_count: int = 0
    reason: str | None = None


@dataclass(frozen=True)
class MemoryLearningResult:
    """Immutable result metrics returned from IMemoryLifecycle."""

    stored_count: int = 0
    promoted_count: int = 0
    invalidated_count: int = 0
    discarded_count: int = 0


def compute_memory_fingerprint(session_id: str, memory_type: MemoryType, content: str) -> str:
    """Compute a SHA-256 canonical hash fingerprint for memory deduplication."""
    norm_content = " ".join(content.lower().split())
    raw_key = f"{session_id}:{memory_type.value}:{norm_content}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
