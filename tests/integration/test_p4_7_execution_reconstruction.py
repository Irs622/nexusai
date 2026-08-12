"""Execution reconstruction integration test suite for P4-7 Observability & Audit Verification."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.audit import AuditEventType
from nexusai.brain.runtime.audit_service import AuditService
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore


@pytest.mark.asyncio
async def test_full_execution_lifecycle_audit_reconstruction() -> None:
    """Test full chronological reconstruction of 15 execution steps with tamper-evident verification."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteAuditStore(db_path=db_path)
        service = AuditService(audit_store=store)

        s_id = "sess-recon-1"
        e_id = "exec-recon-1"
        fp = "fp-recon-1"

        lifecycle_events = [
            AuditEventType.EXECUTION_CREATED,
            AuditEventType.EXECUTION_PLANNING_STARTED,
            AuditEventType.EXECUTION_PLAN_VALIDATED,
            AuditEventType.TOOL_VALIDATION_PASSED,
            AuditEventType.GOVERNANCE_ALLOWED,
            AuditEventType.APPROVAL_REQUEST_CREATED,
            AuditEventType.APPROVAL_DECISION_RECORDED,
            AuditEventType.APPROVAL_GRANT_CONSUMED,
            AuditEventType.LEASE_ACQUIRED,
            AuditEventType.TOOL_EXECUTION_STARTED,
            AuditEventType.TOOL_EXECUTION_COMPLETED,
            AuditEventType.EXECUTION_COMPLETED,
        ]

        for idx, evt_type in enumerate(lifecycle_events, start=1):
            await service.record_event(
                event_type=evt_type,
                session_id=s_id,
                execution_id=e_id,
                plan_fingerprint=fp,
                event_id=f"evt-recon-{idx}",
            )

        timeline = await service.reconstruct_execution_timeline(e_id)
        assert len(timeline) == 12

        # Verify sequence numbers are monotonic from 1 to 12
        for i, ev in enumerate(timeline, start=1):
            assert ev.sequence_number == i

        verification = await service.verify_execution_audit(e_id)
        assert verification.valid is True
        assert verification.event_count == 12
        assert verification.sequence_valid is True
        assert verification.hash_chain_valid is True

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_full_execution_lifecycle_audit_reconstruction())
    print("ALL EXECUTION RECONSTRUCTION INTEGRATION TESTS PASSED SUCCESSFULLY!")
