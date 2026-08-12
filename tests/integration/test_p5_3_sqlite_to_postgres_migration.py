"""SQLite-to-PostgreSQL data migration and audit chain verification integration test suite."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.audit import AuditEvent, AuditEventType
from nexusai.brain.runtime.audit_service import AuditService
from nexusai.infrastructure.persistence.postgres_audit_store import PostgresAuditStore
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore


@pytest.mark.asyncio
async def test_sqlite_to_postgres_migration_and_audit_chain_verification() -> None:
    """Test SQLite-to-PostgreSQL migration preserves tamper-evident hash chain integrity and timeline reconstruction."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        # Step 1: Export events in SQLite store
        sqlite_store = SQLiteAuditStore(db_path=db_path)
        s_id = "sess-mig-1"
        e_id = "exec-mig-1"
        fp = "fp-mig-1"

        ev1 = await sqlite_store.append_event(AuditEvent("e1", AuditEventType.EXECUTION_CREATED.value, s_id, e_id, fp, 0))
        ev2 = await sqlite_store.append_event(AuditEvent("e2", AuditEventType.EXECUTION_STARTED.value, s_id, e_id, fp, 0))
        ev3 = await sqlite_store.append_event(AuditEvent("e3", AuditEventType.EXECUTION_COMPLETED.value, s_id, e_id, fp, 0))

        sqlite_events = await sqlite_store.get_events(e_id)
        assert len(sqlite_events) == 3

        # Step 2: Import into PostgreSQL audit store
        pg_store = PostgresAuditStore()
        for ev in sqlite_events:
            await pg_store.append_event(ev)

        # Step 3: Verify chain integrity & timeline reconstruction post-migration
        pg_service = AuditService(audit_store=pg_store)
        verification = await pg_service.verify_execution_audit(e_id)
        assert verification.valid is True
        assert verification.event_count == 3
        assert verification.hash_chain_valid is True

        timeline = await pg_service.reconstruct_execution_timeline(e_id)
        assert len(timeline) == 3
        assert timeline[0].event_type == AuditEventType.EXECUTION_CREATED.value

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_sqlite_to_postgres_migration_and_audit_chain_verification())
    print("ALL SQLITE-TO-POSTGRES MIGRATION TESTS PASSED SUCCESSFULLY!")
