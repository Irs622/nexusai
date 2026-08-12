"""Reusable domain contract test suite for IApprovalStore implementations (SQLite and PostgreSQL)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalReplayError,
    ApprovalStatus,
    HumanApprovalDecision,
    HumanApprovalRequest,
    RiskLevel,
)
from nexusai.brain.ports.approval_store_port import IApprovalStore
from nexusai.infrastructure.persistence.sqlite_approval_store import SQLiteApprovalStore


async def verify_approval_store_contract(store: IApprovalStore) -> None:
    """Verify any IApprovalStore adapter conforms to the domain contract."""
    binding = ActionBinding(
        session_id="sess-contract-app",
        execution_id="exec-contract-app",
        plan_fingerprint="fp-contract-app",
        node_id="n1",
        tool_id="process_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )

    req = HumanApprovalRequest("app-contract-1", binding, RiskLevel.HIGH, "Run process")
    await store.save_request(req)

    # Retrieve
    ret = await store.get_request("app-contract-1")
    assert ret is not None
    assert ret.status == ApprovalStatus.PENDING

    # Decision
    dec = HumanApprovalDecision("app-contract-1", ApprovalStatus.APPROVED, "op@co.com", "Approved")
    grant = await store.record_decision(dec)

    # Single-use consumption
    assert await store.verify_and_consume_grant(grant.grant_id, binding) is True

    # Replay attempt -> Must fail closed with ApprovalReplayError!
    with pytest.raises(ApprovalReplayError):
        await store.verify_and_consume_grant(grant.grant_id, binding)


@pytest.mark.asyncio
async def test_sqlite_approval_store_conformance() -> None:
    """Test SQLiteApprovalStore conformance to IApprovalStore contract."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteApprovalStore(db_path=db_path)
        await verify_approval_store_contract(store)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_sqlite_approval_store_conformance())
    print("ALL APPROVAL STORE CONTRACT TESTS PASSED SUCCESSFULLY!")
