"""Reusable domain contract test suite for IAuditStore implementations (SQLite and PostgreSQL)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.audit import AuditEvent, AuditEventType, GENESIS_HASH
from nexusai.brain.ports.audit_store_port import IAuditStore
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore


async def verify_audit_store_contract(store: IAuditStore) -> None:
    """Verify any IAuditStore adapter conforms to the domain contract."""
    ev1 = AuditEvent(
        event_id="e-contract-1",
        event_type=AuditEventType.EXECUTION_CREATED.value,
        session_id="s-contract-1",
        execution_id="exec-contract-aud",
        plan_fingerprint="fp-contract-1",
        sequence_number=0,
    )
    res1 = await store.append_event(ev1)
    assert res1.sequence_number == 1
    assert res1.previous_event_hash == GENESIS_HASH

    ev2 = AuditEvent(
        event_id="e-contract-2",
        event_type=AuditEventType.EXECUTION_STARTED.value,
        session_id="s-contract-1",
        execution_id="exec-contract-aud",
        plan_fingerprint="fp-contract-1",
        sequence_number=0,
    )
    res2 = await store.append_event(ev2)
    assert res2.sequence_number == 2
    assert res2.previous_event_hash == res1.event_hash

    # Verify chain
    verification = await store.verify_chain("exec-contract-aud")
    assert verification.valid is True
    assert verification.event_count == 2


@pytest.mark.asyncio
async def test_sqlite_audit_store_conformance() -> None:
    """Test SQLiteAuditStore conformance to IAuditStore contract."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteAuditStore(db_path=db_path)
        await verify_audit_store_contract(store)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_sqlite_audit_store_conformance())
    print("ALL AUDIT STORE CONTRACT TESTS PASSED SUCCESSFULLY!")
