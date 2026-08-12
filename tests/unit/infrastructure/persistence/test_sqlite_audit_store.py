"""Unit test suite for SQLiteAuditStore append, tamper-evident hash chaining, and verification."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.audit import AuditEvent, AuditEventType, GENESIS_HASH
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore


@pytest.mark.asyncio
async def test_sqlite_audit_store_append_and_verify_chain() -> None:
    """Test SQLiteAuditStore appends entries with monotonic sequence numbers and valid SHA-256 hash chains."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteAuditStore(db_path=db_path)

        ev1 = AuditEvent(
            event_id="e1",
            event_type=AuditEventType.EXECUTION_CREATED.value,
            session_id="s1",
            execution_id="exec-1",
            plan_fingerprint="fp1",
            sequence_number=0,
        )
        res1 = await store.append_event(ev1)
        assert res1.sequence_number == 1
        assert res1.previous_event_hash == GENESIS_HASH

        ev2 = AuditEvent(
            event_id="e2",
            event_type=AuditEventType.EXECUTION_STARTED.value,
            session_id="s1",
            execution_id="exec-1",
            plan_fingerprint="fp1",
            sequence_number=0,
        )
        res2 = await store.append_event(ev2)
        assert res2.sequence_number == 2
        assert res2.previous_event_hash == res1.event_hash

        # Verify chain integrity
        verification = await store.verify_chain("exec-1")
        assert verification.valid is True
        assert verification.event_count == 2
        assert verification.sequence_valid is True
        assert verification.hash_chain_valid is True
        assert verification.correlation_valid is True

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_sqlite_audit_store_append_and_verify_chain())
    print("ALL SQLITE AUDIT STORE UNIT TESTS PASSED SUCCESSFULLY!")
