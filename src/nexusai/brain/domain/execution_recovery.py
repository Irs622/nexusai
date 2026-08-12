"""Domain models, recovery status taxonomy, lifecycle phases, and audit journal entries for Crash Recovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import time
from typing import Any, Mapping

from nexusai.brain.domain.observability import sanitize_attributes
from nexusai.brain.domain.tool_registry import ToolIdempotency


class RecoveryStatus(str, Enum):
    """Classification for crash recovery safety decisions."""

    RECOVERABLE = "RECOVERABLE"
    RECOVERABLE_WITH_REVALIDATION = "RECOVERABLE_WITH_REVALIDATION"
    AMBIGUOUS_SIDE_EFFECT = "AMBIGUOUS_SIDE_EFFECT"
    NON_RECOVERABLE = "NON_RECOVERABLE"


class JournalLifecyclePhase(str, Enum):
    """Detailed durable lifecycle phase state machine."""

    CREATED = "CREATED"
    PLANNING = "PLANNING"
    PLAN_VALIDATED = "PLAN_VALIDATED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    GOVERNANCE_RESERVED = "GOVERNANCE_RESERVED"
    READY_TO_EXECUTE = "READY_TO_EXECUTE"
    EXECUTING_TOOL = "EXECUTING_TOOL"
    TOOL_EXECUTED = "TOOL_EXECUTED"
    OBSERVATION_PENDING = "OBSERVATION_PENDING"
    OBSERVATION_PERSISTED = "OBSERVATION_PERSISTED"
    MEMORY_PENDING = "MEMORY_PENDING"
    MEMORY_PERSISTED = "MEMORY_PERSISTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ABANDONED = "ABANDONED"


TERMINAL_JOURNAL_PHASES = frozenset({
    JournalLifecyclePhase.COMPLETED,
    JournalLifecyclePhase.FAILED,
    JournalLifecyclePhase.CANCELLED,
    JournalLifecyclePhase.ABANDONED,
})


@dataclass(frozen=True)
class JournalEntry:
    """Immutable durable record of a single execution lifecycle transition."""

    entry_id: str
    session_id: str
    execution_id: str
    plan_fingerprint: str
    node_id: str
    tool_id: str
    action_digest: str
    phase: JournalLifecyclePhase
    timestamp: float = field(default_factory=time.time)
    attempt: int = 1
    governance_reservation_id: str | None = None
    approval_grant_id: str | None = None
    idempotency_key: str = ""
    idempotency: ToolIdempotency = ToolIdempotency.UNKNOWN
    recovery_status: RecoveryStatus = RecoveryStatus.RECOVERABLE
    audit_hash: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate domain invariants, generate idempotency key & SHA-256 audit hash, sanitize metadata."""
        if not self.entry_id.strip():
            raise ValueError("entry_id cannot be empty")
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if not self.execution_id.strip():
            raise ValueError("execution_id cannot be empty")

        if not self.idempotency_key:
            idem_key = f"{self.execution_id}:{self.node_id}:{self.attempt}"
            object.__setattr__(self, "idempotency_key", idem_key)

        if not self.audit_hash:
            canonical_payload = {
                "entry_id": self.entry_id,
                "session_id": self.session_id,
                "execution_id": self.execution_id,
                "plan_fingerprint": self.plan_fingerprint,
                "node_id": self.node_id,
                "tool_id": self.tool_id,
                "phase": self.phase.value,
                "timestamp": self.timestamp,
            }
            raw_bytes = json.dumps(canonical_payload, sort_keys=True).encode("utf-8")
            digest = hashlib.sha256(raw_bytes).hexdigest()
            object.__setattr__(self, "audit_hash", digest)

        # Secret sanitization invariant
        sanitized = sanitize_attributes(self.metadata)
        object.__setattr__(self, "metadata", sanitized)
