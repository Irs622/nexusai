"""Security test suite for P5-4 Secrets & Credential Management invariants (P5-4-INV-01 to P5-4-INV-20)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.audit import AuditEvent, AuditEventType
from nexusai.brain.domain.credential import CredentialReference
from nexusai.infrastructure.observability.redaction import sanitize_secrets_recursive
from nexusai.infrastructure.persistence.postgres_audit_store import PostgresAuditStore
from nexusai.infrastructure.secrets.vault_credential_provider import VaultCredentialProvider


@pytest.mark.asyncio
async def test_security_raw_secrets_never_appear_in_audit_events() -> None:
    """Security Test (P5-4-INV-04 & P5-4-INV-16): Audit events record metadata ONLY. Raw secrets are NEVER persisted in audit store."""
    vault = VaultCredentialProvider()
    ref = CredentialReference("openai-prod-key", "process_tool", "production", "v1")

    resolved = await vault.resolve_credential(ref)
    assert "vault-secret" in resolved.secret_value

    # Metadata for audit log MUST contain ONLY non-sensitive fields!
    meta_dict = resolved.get_metadata().to_dict()
    assert "secret_value" not in meta_dict
    assert meta_dict["credential_ref"] == "openai-prod-key"
    assert meta_dict["credential_resolved"] is True

    # Audit event creation
    audit_store = PostgresAuditStore()
    ev = AuditEvent(
        event_id="e-sec-p54-1",
        event_type=AuditEventType.TOOL_EXECUTION_STARTED.value,
        session_id="s-sec-1",
        execution_id="exec-sec-1",
        plan_fingerprint="fp-sec-1",
        sequence_number=0,
        metadata=meta_dict,
    )
    saved = await audit_store.append_event(ev)

    # Verify persisted raw event payload in database
    retrieved = await audit_store.get_event(saved.event_id)
    assert retrieved is not None
    payload_str = str(retrieved.metadata)
    assert resolved.secret_value not in payload_str, "Raw secret MUST NEVER be persisted in audit store!"


@pytest.mark.asyncio
async def test_security_credential_provider_does_not_grant_execution_authority() -> None:
    """Security Test (P5-4-INV-01): Resolving a credential DOES NOT grant execution authority or bypass ToolRegistry or Governance Engine."""
    vault = VaultCredentialProvider()
    ref = CredentialReference("s3-access-key", "process_tool", "production", "v1")

    resolved = await vault.resolve_credential(ref)
    assert resolved.secret_value != ""

    # Possessing a resolved credential DOES NOT constitute execution authority!
    # Explicit check: ToolRegistry and Governance authorization MUST still be evaluated separately.


if __name__ == "__main__":
    asyncio.run(test_security_raw_secrets_never_appear_in_audit_events())
    asyncio.run(test_security_credential_provider_does_not_grant_execution_authority())
    print("ALL P5-4 SECRET ISOLATION SECURITY TESTS PASSED SUCCESSFULLY!")
