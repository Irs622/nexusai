"""Unit test suite for SQLiteAuditStore append, tamper-evident hash chaining, and verification.

Exact path specified in GitHub Issue #33: tests/unit/infrastructure/test_sqlite_audit_store.py
"""

from __future__ import annotations

import asyncio
import inspect
import os
import re
import sqlite3
import tempfile

import pytest

from nexusai.brain.domain.audit import GENESIS_HASH, AuditEvent, AuditEventType
from nexusai.infrastructure.persistence import sqlite_audit_store
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


def test_zero_update_or_delete_statements_in_audit_store() -> None:
    """Requirement: The store MUST NOT contain any SQL UPDATE or DELETE statements targeting audit_events."""
    source_code = inspect.getsource(sqlite_audit_store)

    # Search for any SQL UPDATE or DELETE targeting audit_events or tables
    update_matches = re.findall(r"\bUPDATE\s+audit_events\b", source_code, re.IGNORECASE)
    delete_matches = re.findall(r"\bDELETE\s+FROM\s+audit_events\b", source_code, re.IGNORECASE)

    assert len(update_matches) == 0, f"Found forbidden UPDATE statement: {update_matches}"
    assert len(delete_matches) == 0, f"Found forbidden DELETE statement: {delete_matches}"

    # Also search for generic UPDATE or DELETE queries in strings
    generic_update = re.findall(r'["\']\s*UPDATE\b', source_code, re.IGNORECASE)
    generic_delete = re.findall(r'["\']\s*DELETE\b', source_code, re.IGNORECASE)
    assert len(generic_update) == 0, f"Found UPDATE in SQL string: {generic_update}"
    assert len(generic_delete) == 0, f"Found DELETE in SQL string: {generic_delete}"


@pytest.mark.asyncio
async def test_sqlite_audit_store_process_restart_persistence() -> None:
    """Requirement: Audit events survive process restart (persisted across store re-instantiations)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        # Process 1: write 2 events
        store1 = SQLiteAuditStore(db_path=db_path)
        ev1 = AuditEvent(
            event_id="ev-p1-1",
            event_type=AuditEventType.EXECUTION_CREATED.value,
            session_id="s1",
            execution_id="exec-restart-1",
            plan_fingerprint="fp-1",
            sequence_number=0,
            tenant_id="tenant-alpha",
        )
        res1 = await store1.append_event(ev1)
        assert res1.sequence_number == 1

        ev2 = AuditEvent(
            event_id="ev-p1-2",
            event_type=AuditEventType.TOOL_EXECUTION_COMPLETED.value,
            session_id="s1",
            execution_id="exec-restart-1",
            plan_fingerprint="fp-1",
            sequence_number=0,
            tenant_id="tenant-alpha",
        )
        res2 = await store1.append_event(ev2)
        assert res2.sequence_number == 2
        del store1

        # Process 2 (simulated restart): instantiate new store pointing to same SQLite DB
        store2 = SQLiteAuditStore(db_path=db_path)
        events = await store2.get_events(tenant_id="tenant-alpha")
        assert len(events) == 2
        assert events[0].event_id == "ev-p1-1"
        assert events[1].event_id == "ev-p1-2"

        # Next appended event must have sequence 3 and link to ev2's event_hash
        ev3 = AuditEvent(
            event_id="ev-p2-3",
            event_type=AuditEventType.EXECUTION_COMPLETED.value,
            session_id="s1",
            execution_id="exec-restart-1",
            plan_fingerprint="fp-1",
            sequence_number=0,
            tenant_id="tenant-alpha",
        )
        res3 = await store2.append_event(ev3)
        assert res3.sequence_number == 3
        assert res3.previous_event_hash == res2.event_hash

        # Chain across both lifecycles must be 100% valid
        verification = await store2.verify_chain(tenant_id="tenant-alpha")
        assert verification.valid is True
        assert verification.event_count == 3
        assert verification.hash_chain_valid is True
        assert verification.sequence_valid is True

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_sqlite_audit_store_tenant_isolation() -> None:
    """Requirement: Monotonic sequence and hash chain are strictly isolated per tenant."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteAuditStore(db_path=db_path)

        # Tenant A: 2 events
        ev_a1 = await store.append_event(
            AuditEvent(
                event_id="a1",
                event_type="EXECUTION_CREATED",
                session_id="sa",
                execution_id="ea",
                plan_fingerprint="fpa",
                sequence_number=0,
                tenant_id="tenant-A",
            )
        )
        ev_a2 = await store.append_event(
            AuditEvent(
                event_id="a2",
                event_type="EXECUTION_COMPLETED",
                session_id="sa",
                execution_id="ea",
                plan_fingerprint="fpa",
                sequence_number=0,
                tenant_id="tenant-A",
            )
        )

        # Tenant B: 2 events
        ev_b1 = await store.append_event(
            AuditEvent(
                event_id="b1",
                event_type="EXECUTION_CREATED",
                session_id="sb",
                execution_id="eb",
                plan_fingerprint="fpb",
                sequence_number=0,
                tenant_id="tenant-B",
            )
        )
        ev_b2 = await store.append_event(
            AuditEvent(
                event_id="b2",
                event_type="EXECUTION_COMPLETED",
                session_id="sb",
                execution_id="eb",
                plan_fingerprint="fpb",
                sequence_number=0,
                tenant_id="tenant-B",
            )
        )

        # Invariants: Tenant A and B both start sequence at 1
        assert ev_a1.sequence_number == 1
        assert ev_a1.previous_event_hash == GENESIS_HASH
        assert ev_a2.sequence_number == 2
        assert ev_a2.previous_event_hash == ev_a1.event_hash

        assert ev_b1.sequence_number == 1
        assert ev_b1.previous_event_hash == GENESIS_HASH
        assert ev_b2.sequence_number == 2
        assert ev_b2.previous_event_hash == ev_b1.event_hash

        # Scoped queries return only respective tenant events
        events_a = await store.get_events(tenant_id="tenant-A")
        assert [e.event_id for e in events_a] == ["a1", "a2"]

        events_b = await store.get_events(tenant_id="tenant-B")
        assert [e.event_id for e in events_b] == ["b1", "b2"]

        # Both chains verify independently
        res_a = await store.verify_chain(tenant_id="tenant-A")
        assert res_a.valid is True
        assert res_a.event_count == 2

        res_b = await store.verify_chain(tenant_id="tenant-B")
        assert res_b.valid is True
        assert res_b.event_count == 2

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_sqlite_audit_store_startup_integrity_check() -> None:
    """Requirement: Startup integrity check reports break when database has corrupted event."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteAuditStore(db_path=db_path)

        for i in range(1, 4):
            await store.append_event(
                AuditEvent(
                    event_id=f"chk-{i}",
                    event_type="TOOL_EXECUTION_COMPLETED",
                    session_id="s1",
                    execution_id="e1",
                    plan_fingerprint="fp",
                    sequence_number=0,
                    tenant_id="default",
                )
            )

        # Baseline: integrity check passes
        chk1 = await store.startup_integrity_check()
        assert chk1.valid is True
        assert chk1.event_count == 3
        assert chk1.broken_at_sequence is None

        # Simulate external tampering directly on SQLite file
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE audit_events SET outcome = 'TAMPERED_VAL' WHERE id = 'chk-2'")
        conn.commit()
        conn.close()

        # Startup integrity check must detect the break
        chk2 = await store.startup_integrity_check()
        assert chk2.valid is False
        assert chk2.broken_at_sequence == 2
        assert len(chk2.violations) > 0
        assert any("Tampered payload" in v or "Payload tampered" in v for v in chk2.violations)

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_sqlite_audit_store_concurrent_writes_monotonicity() -> None:
    """Requirement: Concurrent event writes maintain sequence monotonicity without duplicate sequence numbers."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteAuditStore(db_path=db_path)

        async def _write(idx: int) -> AuditEvent:
            ev = AuditEvent(
                event_id=f"concurrent-{idx}",
                event_type="TOOL_EXECUTION_COMPLETED",
                session_id="session-concurrent",
                execution_id="exec-concurrent",
                plan_fingerprint="fp-concurrent",
                sequence_number=0,
                tenant_id="tenant-load",
            )
            return await store.append_event(ev)

        results = await asyncio.gather(*[_write(i) for i in range(25)])

        sequences = [r.sequence_number for r in results]
        assert len(sequences) == 25
        assert (
            len(set(sequences)) == 25
        ), "Duplicate sequence numbers detected under concurrent writes!"
        assert sorted(sequences) == list(range(1, 26))

        # Chain verification across all concurrent events
        verification = await store.verify_chain(tenant_id="tenant-load")
        assert verification.valid is True
        assert verification.event_count == 25
        assert verification.sequence_valid is True
        assert verification.hash_chain_valid is True

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
