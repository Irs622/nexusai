"""Domain models, event taxonomy, and audit verification types for P4-7 Observability & Audit Verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import time
from typing import Any, Mapping

from nexusai.infrastructure.observability.redaction import sanitize_secrets_recursive

GENESIS_HASH = "0" * 64


class AuditPrivacyLevel(str, Enum):
    """Privacy preservation levels for LLM prompts and tool arguments."""

    AUDIT_MINIMAL = "AUDIT_MINIMAL"
    AUDIT_STANDARD = "AUDIT_STANDARD"
    AUDIT_DEBUG = "AUDIT_DEBUG"


class AuditEventType(str, Enum):
    """Canonical event taxonomy for governed execution lifecycle auditing."""

    # Execution Lifecycle
    EXECUTION_CREATED = "EXECUTION_CREATED"
    EXECUTION_PLANNING_STARTED = "EXECUTION_PLANNING_STARTED"
    EXECUTION_PLAN_VALIDATED = "EXECUTION_PLAN_VALIDATED"
    EXECUTION_APPROVAL_REQUIRED = "EXECUTION_APPROVAL_REQUIRED"
    EXECUTION_APPROVED = "EXECUTION_APPROVED"
    EXECUTION_DENIED = "EXECUTION_DENIED"
    EXECUTION_CANCELLED = "EXECUTION_CANCELLED"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_COMPLETED = "EXECUTION_COMPLETED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    EXECUTION_ABANDONED = "EXECUTION_ABANDONED"

    # Tool Lifecycle
    TOOL_VALIDATION_STARTED = "TOOL_VALIDATION_STARTED"
    TOOL_VALIDATION_PASSED = "TOOL_VALIDATION_PASSED"
    TOOL_VALIDATION_FAILED = "TOOL_VALIDATION_FAILED"
    TOOL_EXECUTION_STARTED = "TOOL_EXECUTION_STARTED"
    TOOL_EXECUTION_COMPLETED = "TOOL_EXECUTION_COMPLETED"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    TOOL_EXECUTION_BLOCKED = "TOOL_EXECUTION_BLOCKED"

    # Governance
    GOVERNANCE_CHECK_STARTED = "GOVERNANCE_CHECK_STARTED"
    GOVERNANCE_ALLOWED = "GOVERNANCE_ALLOWED"
    GOVERNANCE_DENIED = "GOVERNANCE_DENIED"
    GOVERNANCE_RESERVATION_CREATED = "GOVERNANCE_RESERVATION_CREATED"
    GOVERNANCE_RESERVATION_RELEASED = "GOVERNANCE_RESERVATION_RELEASED"
    GOVERNANCE_RESERVATION_ORPHANED = "GOVERNANCE_RESERVATION_ORPHANED"

    # Approval
    APPROVAL_REQUEST_CREATED = "APPROVAL_REQUEST_CREATED"
    APPROVAL_DECISION_RECORDED = "APPROVAL_DECISION_RECORDED"
    APPROVAL_GRANT_CONSUMED = "APPROVAL_GRANT_CONSUMED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_REPLAY_BLOCKED = "APPROVAL_REPLAY_BLOCKED"

    # Recovery
    RECOVERY_SCAN_STARTED = "RECOVERY_SCAN_STARTED"
    RECOVERY_CLASSIFIED = "RECOVERY_CLASSIFIED"
    RECOVERY_REVALIDATION_STARTED = "RECOVERY_REVALIDATION_STARTED"
    RECOVERY_REVALIDATION_FAILED = "RECOVERY_REVALIDATION_FAILED"
    RECOVERY_RESUMED = "RECOVERY_RESUMED"
    RECOVERY_ABANDONED = "RECOVERY_ABANDONED"

    # Distributed Coordination
    LEASE_ACQUIRED = "LEASE_ACQUIRED"
    LEASE_RENEWED = "LEASE_RENEWED"
    LEASE_RELEASED = "LEASE_RELEASED"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    LEASE_TAKEOVER = "LEASE_TAKEOVER"
    FENCING_TOKEN_REJECTED = "FENCING_TOKEN_REJECTED"
    STALE_WORKER_REJECTED = "STALE_WORKER_REJECTED"

    # LLM
    LLM_REQUEST_STARTED = "LLM_REQUEST_STARTED"
    LLM_RESPONSE_RECEIVED = "LLM_RESPONSE_RECEIVED"
    LLM_RESPONSE_REJECTED = "LLM_RESPONSE_REJECTED"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"

    # Security
    SECURITY_GATE_BLOCKED = "SECURITY_GATE_BLOCKED"
    CAPABILITY_ESCALATION_BLOCKED = "CAPABILITY_ESCALATION_BLOCKED"
    PLAN_FINGERPRINT_MISMATCH = "PLAN_FINGERPRINT_MISMATCH"
    ACTION_DIGEST_MISMATCH = "ACTION_DIGEST_MISMATCH"
    SESSION_BOUNDARY_VIOLATION = "SESSION_BOUNDARY_VIOLATION"
    TOOL_REVOKED = "TOOL_REVOKED"
    SSRF_BLOCKED = "SSRF_BLOCKED"
    SANDBOX_ESCAPE_BLOCKED = "SANDBOX_ESCAPE_BLOCKED"


@dataclass(frozen=True)
class AuditEvent:
    """Immutable domain representation of a tamper-evident audit event."""

    event_id: str
    event_type: str
    session_id: str
    execution_id: str
    plan_fingerprint: str
    sequence_number: int
    timestamp: float = field(default_factory=time.time)
    node_id: str | None = None
    tool_id: str | None = None
    worker_id: str | None = None
    fencing_token: int | None = None
    actor: str | None = None
    outcome: str = "SUCCESS"
    severity: str = "INFO"
    previous_event_hash: str = GENESIS_HASH
    event_hash: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate domain invariants, sanitize secret attributes, and compute SHA-256 event hash."""
        if not self.event_id.strip():
            raise ValueError("event_id cannot be empty")
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if not self.execution_id.strip():
            raise ValueError("execution_id cannot be empty")

        # Secret sanitization invariant
        sanitized = sanitize_secrets_recursive(self.metadata)
        object.__setattr__(self, "metadata", sanitized)

        if not self.event_hash:
            canonical_payload = {
                "event_id": self.event_id,
                "event_type": self.event_type,
                "session_id": self.session_id,
                "execution_id": self.execution_id,
                "plan_fingerprint": self.plan_fingerprint,
                "sequence_number": self.sequence_number,
                "timestamp": self.timestamp,
                "previous_event_hash": self.previous_event_hash,
            }
            raw_bytes = json.dumps(canonical_payload, sort_keys=True).encode("utf-8")
            digest = hashlib.sha256(raw_bytes).hexdigest()
            object.__setattr__(self, "event_hash", digest)


@dataclass(frozen=True)
class AuditVerificationResult:
    """Structured report returned by audit chain verification."""

    valid: bool
    event_count: int
    sequence_valid: bool
    hash_chain_valid: bool
    correlation_valid: bool
    terminal_state_valid: bool
    violations: list[str] = field(default_factory=list)
