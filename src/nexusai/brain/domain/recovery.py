"""Domain models for disaster recovery lifecycle, snapshot metadata, and recovery epoch tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Sequence

# Re-exports for backward compatibility with Phase 2/3/4 execution recovery
from nexusai.brain.domain.execution_recovery import (
    JournalEntry,
    JournalLifecyclePhase,
    RecoveryStatus as ExecutionRecoveryStatus,
)


def classify_failure(exc: Exception | None = None) -> FailureClass:
    """Classify exception into a FailureClass."""
    if exc is None:
        return FailureClass.TRANSIENT
    name = type(exc).__name__.lower()
    if "timeout" in name or "connection" in name:
        return FailureClass.TRANSIENT
    if "permission" in name or "auth" in name or "security" in name:
        return FailureClass.GOVERNANCE_VIOLATION
    if "cancel" in name:
        return FailureClass.CANCELLED
    return FailureClass.PERMANENT


def generate_idempotency_key(execution_id: str, node_id: str, attempt: int = 1) -> str:
    """Generate a canonical idempotency key."""
    return f"{execution_id}:{node_id}:{attempt}"


@dataclass(frozen=True)
class ToolExecutionPolicy:
    """Policy governing tool execution retries and timeouts."""

    max_retries: int = 3
    timeout_seconds: float = 30.0
    retry_delay_seconds: float = 1.0


class RecoveryPolicyEngine:
    """Engine for evaluating recovery decisions."""

    @staticmethod
    def evaluate(failure_class: FailureClass, attempt: int = 1, max_retries: int = 3) -> RecoveryDecision:
        if failure_class == FailureClass.TRANSIENT and attempt <= max_retries:
            return RecoveryDecision(
                action=RecoveryAction.RETRY,
                failure_class=failure_class,
                reason=f"Transient failure on attempt {attempt}/{max_retries}",
                retry_delay_seconds=1.0 * attempt,
            )
        return RecoveryDecision(
            action=RecoveryAction.SAFE_ABANDON,
            failure_class=failure_class,
            reason=f"Non-retryable failure class {failure_class.value}",
        )



class FailureClass(str, Enum):
    """Classification of execution failures."""

    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"
    GOVERNANCE_VIOLATION = "GOVERNANCE_VIOLATION"
    SIDE_EFFECT_AMBIGUOUS = "SIDE_EFFECT_AMBIGUOUS"
    CANCELLED = "CANCELLED"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"


class RecoveryAction(str, Enum):
    """Recommended recovery action."""

    RETRY = "RETRY"
    REVALIDATE_AND_RETRY = "REVALIDATE_AND_RETRY"
    SAFE_ABANDON = "SAFE_ABANDON"
    QUARANTINE = "QUARANTINE"
    HUMAN_INTERVENTION = "HUMAN_INTERVENTION"


@dataclass(frozen=True)
class RecoveryDecision:
    """Decision payload produced by recovery evaluation."""

    action: RecoveryAction
    failure_class: FailureClass
    reason: str
    requires_approval: bool = False
    retry_delay_seconds: float = 0.0
    idempotency_key: str = ""
    next_retry_at: float | None = None


class RecoveryStatus(str, Enum):
    """Lifecycle state of a disaster recovery operation."""

    DETECTED = "DETECTED"
    VALIDATING = "VALIDATING"
    RESTORING = "RESTORING"
    RECONCILING = "RECONCILING"
    VERIFYING = "VERIFYING"
    READY = "READY"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True)
class BackupMetadata:
    """Non-sensitive metadata describing a durable database snapshot/backup artifact."""

    backup_id: str
    created_at: float
    database_system: str
    database_version: str
    schema_version: str
    checksum_sha256: str
    size_bytes: int
    recovery_point_timestamp: float
    retention_until: float
    is_encrypted: bool = True
    verification_status: str = "VERIFIED"


@dataclass(frozen=True)
class DisasterRecoveryPolicy:
    """Policy bounds for RPO/RTO targets and automated snapshot intervals."""

    rpo_target_seconds: float = 300.0  # 5 minutes
    rto_target_seconds: float = 900.0  # 15 minutes
    backup_interval_seconds: float = 3600.0
    retention_days: int = 30
    require_checksum_verification: bool = True


@dataclass(frozen=True)
class RecoveryVerificationResult:
    """Diagnostic outcome of recovery consistency and security invariant checks."""

    valid: bool
    recovery_epoch: int
    journal_reconciled_count: int
    invalidated_leases_count: int
    audit_chain_valid: bool
    violations: Sequence[str] = field(default_factory=list)


@dataclass(frozen=True)
class RecoveryResult:
    """Final output payload of a disaster recovery drill or operation."""

    recovery_id: str
    backup_id: str
    status: RecoveryStatus
    recovery_epoch: int
    duration_ms: float
    verification: RecoveryVerificationResult
