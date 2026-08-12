"""Security verification test suite for P5-3 Durable Distributed Persistence invariants."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.human_approval import ActionBinding, ApprovalReplayError, ApprovalStatus, HumanApprovalDecision, HumanApprovalRequest, RiskLevel
from nexusai.infrastructure.persistence.postgres_approval_store import PostgresApprovalStore


@pytest.mark.asyncio
async def test_security_postgres_persistence_authorization_invariants() -> None:
    """Security Test: Changing persistence backend to PostgreSQL does NOT weaken single-use grant replay protection."""
    store = PostgresApprovalStore()

    binding = ActionBinding(
        session_id="sess-p53-sec",
        execution_id="exec-p53-sec",
        plan_fingerprint="fp-p53-sec",
        node_id="n1",
        tool_id="process_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )

    req = HumanApprovalRequest("app-p53-sec-1", binding, RiskLevel.HIGH, "Run process")
    await store.save_request(req)

    dec = HumanApprovalDecision("app-p53-sec-1", ApprovalStatus.APPROVED, "op@co.com", "Approved")
    grant = await store.record_decision(dec)

    # First consumption succeeds
    assert await store.verify_and_consume_grant(grant.grant_id, binding) is True

    # Replay attempt MUST fail closed with ApprovalReplayError!
    with pytest.raises(ApprovalReplayError):
        await store.verify_and_consume_grant(grant.grant_id, binding)


if __name__ == "__main__":
    asyncio.run(test_security_postgres_persistence_authorization_invariants())
    print("ALL P5-3 PERSISTENCE SECURITY TESTS PASSED SUCCESSFULLY!")
