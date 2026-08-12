"""Protocol port interfaces for disaster recovery, snapshot management, and backup integrity verification."""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from nexusai.brain.domain.recovery import (
    BackupMetadata,
    RecoveryResult,
    RecoveryStatus,
    RecoveryVerificationResult,
)


@runtime_checkable
class IDurableBackupProvider(Protocol):
    """Protocol interface for durable database snapshot and backup management."""

    async def create_backup(self, backup_id: str) -> BackupMetadata:
        """Create a durable snapshot backup."""
        ...

    async def list_backups(self) -> Sequence[BackupMetadata]:
        """List available recovery points."""
        ...

    async def get_backup(self, backup_id: str) -> BackupMetadata | None:
        """Retrieve backup metadata by backup_id."""
        ...


@runtime_checkable
class IBackupIntegrityVerifier(Protocol):
    """Protocol interface for validating cryptographic backup checksums prior to restore."""

    async def verify_backup_integrity(self, metadata: BackupMetadata) -> bool:
        """Verify checksum SHA-256 and payload completeness."""
        ...


@runtime_checkable
class IRecoveryManager(Protocol):
    """Protocol interface for executing disaster recovery lifecycle, lease invalidation, and recovery epoch increments."""

    async def execute_disaster_recovery(self, backup_id: str) -> RecoveryResult:
        """Execute full disaster recovery procedure."""
        ...

    async def get_current_recovery_epoch(self) -> int:
        """Retrieve current system recovery epoch generation."""
        ...
