"""Reusable contract test suite for IDurableBackupProvider and IRecoveryManager."""

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
async def test_disaster_recovery_contract_conformance() -> None:
    """Verify disaster recovery implementation satisfies recovery epoch increment and status transition contract."""
    backup_prov = PostgresBackupProvider()
    verifier = BackupIntegrityVerifier()
    coord = PostgresExecutionCoordinator()
    audit_store = PostgresAuditStore()

    rec_mgr = DisasterRecoveryManager(backup_prov, verifier, coord, audit_store)
    epoch_initial = await rec_mgr.get_current_recovery_epoch()

    # Create backup
    meta = await backup_prov.create_backup("bak-contract-1")
    assert meta.backup_id == "bak-contract-1"

    # Execute recovery drill
    res = await rec_mgr.execute_disaster_recovery("bak-contract-1")
    assert res.status == RecoveryStatus.READY
    assert res.recovery_epoch == epoch_initial + 1
    assert res.verification.valid is True


if __name__ == "__main__":
    asyncio.run(test_disaster_recovery_contract_conformance())
    print("ALL DISASTER RECOVERY CONTRACT TESTS PASSED SUCCESSFULLY!")
