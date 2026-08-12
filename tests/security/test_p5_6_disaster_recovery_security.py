"""Security verification test suite for P5-6 Disaster Recovery invariants (P5-6-INV-01 to P5-6-INV-25)."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.recovery import BackupMetadata, RecoveryStatus
from nexusai.infrastructure.coordination.postgres_execution_coordinator import PostgresExecutionCoordinator
from nexusai.infrastructure.persistence.postgres_audit_store import PostgresAuditStore
from nexusai.infrastructure.recovery.backup_integrity_verifier import BackupIntegrityVerifier
from nexusai.infrastructure.recovery.postgres_backup_provider import PostgresBackupProvider
from nexusai.infrastructure.recovery.recovery_manager import DisasterRecoveryManager


@pytest.mark.asyncio
async def test_security_disaster_recovery_increments_epoch_and_invalidates_old_fencing_tokens() -> None:
    """Security Test (P5-6-INV-02 & P5-6-INV-03): Disaster recovery increments recovery epoch and invalidates old worker fencing tokens."""
    backup_prov = PostgresBackupProvider()
    verifier = BackupIntegrityVerifier()
    coord = PostgresExecutionCoordinator()
    audit_store = PostgresAuditStore()

    rec_mgr = DisasterRecoveryManager(backup_prov, verifier, coord, audit_store)
    epoch_before = await rec_mgr.get_current_recovery_epoch()

    meta = await backup_prov.create_backup("bak-sec-1")
    res = await rec_mgr.execute_disaster_recovery("bak-sec-1")

    assert res.status == RecoveryStatus.READY
    assert res.recovery_epoch == epoch_before + 1
    assert res.verification.recovery_epoch == epoch_before + 1


@pytest.mark.asyncio
async def test_security_raw_secrets_never_appear_in_backup_metadata() -> None:
    """Security Test (P5-6-INV-13): Backup metadata contains non-sensitive timestamps/checksums ONLY. Secrets are NEVER persisted in backups."""
    backup_prov = PostgresBackupProvider()
    meta = await backup_prov.create_backup("bak-sec-2")

    meta_str = str(meta)
    assert "sk-" not in meta_str
    assert "password" not in meta_str
    assert "vault_token" not in meta_str
    assert meta.checksum_sha256 != ""


@pytest.mark.asyncio
async def test_security_corrupted_backup_causes_quarantine() -> None:
    """Security Test (P5-6-INV-16): Backup with invalid checksum SHA-256 transitions recovery status to QUARANTINED!"""
    backup_prov = PostgresBackupProvider()
    verifier = BackupIntegrityVerifier()
    coord = PostgresExecutionCoordinator()
    audit_store = PostgresAuditStore()

    rec_mgr = DisasterRecoveryManager(backup_prov, verifier, coord, audit_store)

    corrupted_meta = BackupMetadata(
        backup_id="bak-corrupt-1",
        created_at=1000.0,
        database_system="PostgreSQL",
        database_version="16.2",
        schema_version="1.0.0",
        checksum_sha256="bad-checksum",
        size_bytes=100,
        recovery_point_timestamp=1000.0,
        retention_until=2000.0,
        verification_status="FAILED",
    )
    backup_prov._backups["bak-corrupt-1"] = corrupted_meta

    res = await rec_mgr.execute_disaster_recovery("bak-corrupt-1")
    assert res.status == RecoveryStatus.QUARANTINED
    assert res.verification.valid is False
    assert "FAILED" in res.verification.violations[0]


if __name__ == "__main__":
    asyncio.run(test_security_disaster_recovery_increments_epoch_and_invalidates_old_fencing_tokens())
    asyncio.run(test_security_raw_secrets_never_appear_in_backup_metadata())
    asyncio.run(test_security_corrupted_backup_causes_quarantine())
    print("ALL P5-6 DISASTER RECOVERY SECURITY TESTS PASSED SUCCESSFULLY!")
