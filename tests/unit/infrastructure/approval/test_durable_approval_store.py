"""Unit test suite for SQLiteApprovalStore persistence, atomic decision transitions, and single-use grant replay protection."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import pytest

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalExpiredError,
    ApprovalMismatchError,
    ApprovalReplayError,
    ApprovalStatus,
    HumanApprovalDecision,
    HumanApprovalRequest,
    RiskLevel,
)
from nexusai.infrastructure.persistence.sqlite_approval_store import SQLiteApprovalStore


@pytest.mark.asyncio
async def test_durable_approval_store_crud_and_atomic_decision() -> None:
    """Test SQLiteApprovalStore create, read, decision transitions, and single-use grant consumption."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteApprovalStore(db_path=db_path)

        binding = ActionBinding(
            session_id="sess-dur-1",
            execution_id="exec-dur-1",
            plan_fingerprint="fp-dur-1",
            node_id="n1",
            tool_id="process_tool",
            tool_version="1.0.0",
            requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        )

        req = HumanApprovalRequest("app-dur-1", binding, RiskLevel.HIGH, "Run process")
        await store.save_request(req)

        # Retrieve request
        ret_req = await store.get_request("app-dur-1")
        assert ret_req is not None
        assert ret_req.status == ApprovalStatus.PENDING

        # Submit APPROVED decision
        dec = HumanApprovalDecision("app-dur-1", ApprovalStatus.APPROVED, "op@co.com", "Approved")
        grant = await store.record_decision(dec)
        assert grant.grant_id == "grant-app-dur-1"
        assert grant.actor == "op@co.com"

        # Verify & Consume Grant
        assert await store.verify_and_consume_grant(grant.grant_id, binding) is True

        # Replay attempt -> Must fail with ApprovalReplayError
        with pytest.raises(ApprovalReplayError):
            await store.verify_and_consume_grant(grant.grant_id, binding)

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_durable_approval_store_crud_and_atomic_decision())
    print("ALL DURABLE APPROVAL STORE UNIT TESTS PASSED SUCCESSFULLY!")
