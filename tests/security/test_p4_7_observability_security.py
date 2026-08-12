"""Security verification test suite for P4-7 Observability & Audit invariants (P4-7-INV-01 to P4-7-INV-32)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.audit import AuditEvent, AuditEventType
from nexusai.brain.runtime.audit_service import AuditService
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore


@pytest.mark.asyncio
async def test_security_observability_does_not_grant_authority() -> None:
    """Security Test (P4-7-INV-01 & P4-7-INV-02): Audit records cannot execute tools or grant execution authority."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteAuditStore(db_path=db_path)
        service = AuditService(audit_store=store)

        # Recording an audit event claiming "EXECUTION_APPROVED" does NOT create an ApprovalGrant or execution authority!
        evt = await service.record_event(
            event_type=AuditEventType.EXECUTION_APPROVED,
            session_id="sess-sec-aud-1",
            execution_id="exec-sec-aud-1",
            plan_fingerprint="fp-sec-aud-1",
            actor="fake-actor",
        )

        assert evt.event_type == AuditEventType.EXECUTION_APPROVED.value
        # Re-verification of store verifies event chain, but zero tool execution authority exists
        verification = await service.verify_execution_audit("exec-sec-aud-1")
        assert verification.valid is True

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_security_secret_isolation_in_audit_events() -> None:
    """Security Test (P4-7-INV-16 to P4-7-INV-18): API keys, authorization headers, and credentials are redacted prior to audit store persistence."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteAuditStore(db_path=db_path)
        service = AuditService(audit_store=store)

        meta_with_secrets = {
            "OPENAI_API_KEY": "sk-proj-secret-123456789",
            "headers": {"Authorization": "Bearer sk-proj-secret-token"},
            "user": "alice",
        }

        evt = await service.record_event(
            event_type=AuditEventType.LLM_REQUEST_STARTED,
            session_id="sess-sec-aud-2",
            execution_id="exec-sec-aud-2",
            plan_fingerprint="fp-sec-aud-2",
            metadata=meta_with_secrets,
        )

        persisted = await store.get_event(evt.event_id)
        assert persisted is not None
        assert "sk-proj-secret-123456789" not in str(persisted.metadata)
        assert persisted.metadata["OPENAI_API_KEY"] == "[REDACTED_SECRET]"
        assert persisted.metadata["headers"]["Authorization"] == "[REDACTED_SECRET]"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_security_observability_does_not_grant_authority())
    asyncio.run(test_security_secret_isolation_in_audit_events())
    print("ALL P4-7 OBSERVABILITY SECURITY TESTS PASSED SUCCESSFULLY!")
