"""Disaster recovery drill integration test suite for P5-6."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.recovery import RecoveryStatus
from nexusai.infrastructure.coordination.postgres_execution_coordinator import PostgresExecutionCoordinator
from nexusai.infrastructure.persistence.postgres_audit_store import PostgresAuditStore
from nexusai.infrastructure.recovery.backup_integrity_verifier import BackupIntegrityVerifier
from nexusai.infrastructure.recovery.postgres_backup_provider import PostgresBackupProvider
from nexusai.infrastructure.recovery.recovery_manager import DisasterRecoveryManager


@pytest.mark.asyncio
async def test_disaster_recovery_drill_execution() -> None:
    """Integration Test: Full 10-step disaster recovery drill execution."""
    backup_prov = PostgresBackupProvider()
    verifier = BackupIntegrityVerifier()
    coord = PostgresExecutionCoordinator()
    audit_store = PostgresAuditStore()

    # Step 1: Automated backup creation
    meta = await backup_prov.create_backup("bak-drill-100")
    assert meta.checksum_sha256 != ""

    # Step 2: Disaster Recovery Manager startup & recovery drill
    rec_mgr = DisasterRecoveryManager(backup_prov, verifier, coord, audit_store)
    res = await rec_mgr.execute_disaster_recovery("bak-drill-100")

    # Step 3: Verify recovery readiness & epoch increment
    assert res.status == RecoveryStatus.READY
    assert res.recovery_epoch == 2
    assert res.verification.valid is True
    assert res.verification.audit_chain_valid is True
    assert res.verification.invalidated_leases_count > 0


if __name__ == "__main__":
    asyncio.run(test_disaster_recovery_drill_execution())
    print("ALL DISASTER RECOVERY DRILL TESTS PASSED SUCCESSFULLY!")
