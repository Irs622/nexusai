"""Domain models for disaster recovery lifecycle, snapshot metadata, and recovery epoch tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Sequence


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
