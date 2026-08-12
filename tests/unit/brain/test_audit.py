"""Unit test suite for audit domain models, AuditEvent SHA-256 calculation, and AuditVerificationResult."""

from __future__ import annotations

import pytest

from nexusai.brain.domain.audit import AuditEvent, AuditEventType, AuditVerificationResult, GENESIS_HASH


def test_audit_event_domain_model_and_hash_calculation() -> None:
    """Test AuditEvent SHA-256 event_hash calculation and metadata secret redaction."""
    event = AuditEvent(
        event_id="evt-1",
        event_type=AuditEventType.EXECUTION_CREATED.value,
        session_id="sess-1",
        execution_id="exec-1",
        plan_fingerprint="fp-1",
        sequence_number=1,
        previous_event_hash=GENESIS_HASH,
        metadata={"user": "alice", "api_key": "secret-key-12345"},
    )

    assert event.event_id == "evt-1"
    assert event.sequence_number == 1
    assert event.previous_event_hash == GENESIS_HASH
    assert len(event.event_hash) == 64
    assert event.metadata["user"] == "alice"
    assert event.metadata["api_key"] == "[REDACTED_SECRET]"


if __name__ == "__main__":
    test_audit_event_domain_model_and_hash_calculation()
    print("ALL AUDIT DOMAIN UNIT TESTS PASSED SUCCESSFULLY!")
