"""Concurrent audit event writers integration test suite for P4-7."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.audit import AuditEvent, AuditEventType
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore


@pytest.mark.asyncio
async def test_concurrent_audit_event_writers() -> None:
    """Stress Test: 50 concurrent audit event writers appending entries in parallel.

    Invariants: Atomic sequence allocation, zero sequence collisions, 100% tamper-evident chain validity.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteAuditStore(db_path=db_path)

        async def append_worker(w_idx: int) -> AuditEvent:
            ev = AuditEvent(
                event_id=f"evt-conc-{w_idx}",
                event_type=AuditEventType.TOOL_EXECUTION_COMPLETED.value,
                session_id="sess-conc-1",
                execution_id="exec-conc-1",
                plan_fingerprint="fp-conc-1",
                sequence_number=0,
            )
            return await store.append_event(ev)

        tasks = [asyncio.create_task(append_worker(i)) for i in range(50)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 50

        # Verify sequence numbers are strictly 1..50 unique
        seq_numbers = {r.sequence_number for r in results}
        assert len(seq_numbers) == 50
        assert seq_numbers == set(range(1, 51))

        # Verify tamper-evident hash chain across all 50 events
        verification = await store.verify_chain("exec-conc-1")
        assert verification.valid is True
        assert verification.event_count == 50
        assert verification.sequence_valid is True
        assert verification.hash_chain_valid is True

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_concurrent_audit_event_writers())
    print("ALL CONCURRENT AUDIT TESTS PASSED SUCCESSFULLY!")
