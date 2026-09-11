"""Domain models for disaster recovery lifecycle, snapshot metadata, and recovery epoch tracking."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

# Re-exports for backward compatibility with Phase 2/3/4 execution recovery


def classify_failure(
    exc: Exception | None = None, error_message: str | None = None
) -> FailureClass:
    """Classify exception or error message into a FailureClass."""
    msg = ""
    if error_message:
        msg += error_message + " "
    if exc:
        msg += type(exc).__name__ + " " + str(exc)
    msg_lower = msg.strip().lower()

    if "timed out" in msg_lower or "timeout" in msg_lower:
        return FailureClass.TIMEOUT
    if "401" in msg_lower or "unauthorized" in msg_lower or "authentication" in msg_lower:
        return FailureClass.AUTHENTICATION_ERROR
    if "403" in msg_lower or "forbidden" in msg_lower or "authorization" in msg_lower:
        return FailureClass.AUTHORIZATION_ERROR
    if "404" in msg_lower or "not found" in msg_lower:
        return FailureClass.TOOL_NOT_FOUND
    if "invalid argument" in msg_lower:
        return FailureClass.INVALID_ARGUMENT
    if "429" in msg_lower or "rate limit" in msg_lower:
        return FailureClass.RATE_LIMITED
    if "connection refused" in msg_lower or "socket error" in msg_lower or "network" in msg_lower:
        return FailureClass.NETWORK_ERROR
    if "cancel" in msg_lower:
        return FailureClass.CANCELLED
    if "permission" in msg_lower or "security" in msg_lower:
        return FailureClass.GOVERNANCE_VIOLATION
    if "transient" in msg_lower:
        return FailureClass.TRANSIENT_ERROR
    if not msg_lower:
        return FailureClass.TRANSIENT
    return FailureClass.UNKNOWN_ERROR


def generate_idempotency_key(
    execution_id: str, node_id: Any, attempt: int = 1, tenant_id: str | None = None
) -> str:
    """Generate a canonical idempotency key, optionally scoped to tenant."""
    if tenant_id and tenant_id != "default":
        return f"{tenant_id}:{execution_id}-{node_id}:{attempt}"
    return f"{execution_id}-{node_id}:{attempt}"


@dataclass(frozen=True)
class ToolExecutionPolicy:
    """Policy governing tool execution retries, timeouts, and idempotency."""

    idempotent: bool = False
    retryable: bool = True
    side_effecting: bool = False
    max_retries: int = 3
    timeout_seconds: float = 30.0
    retry_delay_seconds: float = 1.0
    backoff_factor: float = 2.0
    max_backoff_seconds: float = 10.0


class FailureClass(str, Enum):
    """Classification of execution failures."""

    TIMEOUT = "TIMEOUT"
    TRANSIENT = "TRANSIENT"
    TRANSIENT_ERROR = "TRANSIENT_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    RATE_LIMITED = "RATE_LIMITED"
    NETWORK_ERROR = "NETWORK_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    PERMANENT = "PERMANENT"
    GOVERNANCE_VIOLATION = "GOVERNANCE_VIOLATION"
    SIDE_EFFECT_AMBIGUOUS = "SIDE_EFFECT_AMBIGUOUS"
    CANCELLED = "CANCELLED"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"


class RecoveryAction(str, Enum):
    """Recommended recovery action."""

    RETRY = "RETRY"
    FAIL = "FAIL"
    RECONCILE = "RECONCILE"
    CANCEL = "CANCEL"
    SAFE_ABANDON = "SAFE_ABANDON"
    REVALIDATE_AND_RETRY = "REVALIDATE_AND_RETRY"
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


class RecoveryPolicyEngine:
    """Engine for evaluating recovery decisions."""

    @staticmethod
    def calculate_backoff(policy: ToolExecutionPolicy, attempt_number: int) -> float:
        delay = 0.5 * (policy.backoff_factor ** (attempt_number - 1))
        return min(delay, policy.max_backoff_seconds)

    @staticmethod
    def evaluate(
        policy: ToolExecutionPolicy | FailureClass | None = None,
        failure_class: FailureClass | None = None,
        attempt_number: int = 1,
        idempotency_key: str = "",
        cb_is_open: bool = False,
        current_time: float | None = None,
        max_retries: int | None = None,
        attempt: int | None = None,
    ) -> RecoveryDecision:
        if isinstance(policy, FailureClass) and failure_class is None:
            failure_class = policy
            policy = ToolExecutionPolicy()

        if attempt is not None and attempt_number == 1:
            attempt_number = attempt

        pol = policy if isinstance(policy, ToolExecutionPolicy) else ToolExecutionPolicy()
        fc = failure_class or FailureClass.UNKNOWN_ERROR
        effective_max_retries = max_retries if max_retries is not None else pol.max_retries

        if cb_is_open:
            return RecoveryDecision(
                action=RecoveryAction.FAIL,
                failure_class=fc,
                reason="CircuitBreaker is OPEN",
                idempotency_key=idempotency_key,
            )

        if fc in (
            FailureClass.AUTHENTICATION_ERROR,
            FailureClass.AUTHORIZATION_ERROR,
            FailureClass.GOVERNANCE_VIOLATION,
        ):
            return RecoveryDecision(
                action=RecoveryAction.FAIL,
                failure_class=fc,
                reason=f"Non-retryable failure: {fc.value}",
                idempotency_key=idempotency_key,
            )

        if fc in (
            FailureClass.TIMEOUT,
            FailureClass.TRANSIENT,
            FailureClass.TRANSIENT_ERROR,
            FailureClass.NETWORK_ERROR,
            FailureClass.RATE_LIMITED,
        ):
            if not pol.idempotent and pol.side_effecting:
                return RecoveryDecision(
                    action=RecoveryAction.RECONCILE,
                    failure_class=fc,
                    reason=f"Non-idempotent side-effecting failure requires reconciliation: {fc.value}",
                    idempotency_key=idempotency_key,
                )
            if attempt_number >= effective_max_retries:
                return RecoveryDecision(
                    action=RecoveryAction.FAIL,
                    failure_class=fc,
                    reason=f"Exceeded max retry budget ({effective_max_retries})",
                    idempotency_key=idempotency_key,
                )
            delay = RecoveryPolicyEngine.calculate_backoff(pol, attempt_number)
            return RecoveryDecision(
                action=RecoveryAction.RETRY,
                failure_class=fc,
                reason=f"Transient failure on attempt {attempt_number}/{effective_max_retries}",
                retry_delay_seconds=delay,
                idempotency_key=idempotency_key,
                next_retry_at=(current_time or time.time()) + delay,
            )

        if not pol.idempotent and pol.side_effecting:
            return RecoveryDecision(
                action=RecoveryAction.RECONCILE,
                failure_class=fc,
                reason=f"Unknown failure on side-effecting tool requires reconciliation: {fc.value}",
                idempotency_key=idempotency_key,
            )

        return RecoveryDecision(
            action=RecoveryAction.FAIL,
            failure_class=fc,
            reason=f"Non-retryable failure class {fc.value}",
            idempotency_key=idempotency_key,
        )


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
