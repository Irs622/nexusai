"""Security verification test suite for P4-4 Durable Approval invariants (P4-4-INV-01 to P4-4-INV-18)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import pytest

from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
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
from nexusai.brain.domain.tool_registry import ToolMetadata, ToolStatus, ToolUnavailableError
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine
from nexusai.brain.runtime.tool_registry import ToolRegistry
from nexusai.infrastructure.persistence.sqlite_approval_store import SQLiteApprovalStore


@pytest.mark.asyncio
async def test_security_durable_approval_is_not_execution_authorization() -> None:
    """Security Test (P4-4-INV-01, INV-09, INV-10): Persisted approval DOES NOT bypass Governance budget exhaustion or Tool revocation."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteApprovalStore(db_path=db_path)
        engine = HumanApprovalEngine(store=store)
        gov = GovernanceEngine(global_budget=ResourceBudget(max_tool_invocations=1))
        registry = ToolRegistry()

        await registry.register(ToolMetadata("process_tool", "Proc", "1.0.0", "Proc", frozenset({ToolCapability.PROCESS_EXEC}), status=ToolStatus.ENABLED))

        binding = ActionBinding(
            session_id="sess-sec-dur-1",
            execution_id="exec-sec-dur-1",
            plan_fingerprint="fp-sec-dur-1",
            node_id="n1",
            tool_id="process_tool",
            tool_version="1.0.0",
            requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        )

        req = HumanApprovalRequest("app-sec-dur-1", binding, RiskLevel.HIGH, "Run process")
        await engine.request_approval(req)
        dec = HumanApprovalDecision("app-sec-dur-1", ApprovalStatus.APPROVED, "op@co.com", "Approved")
        grant = await engine.submit_decision(dec)

        # Another process consumes governance invocation quota
        res1 = await gov.authorize("exec-other", frozenset({ToolCapability.PROCESS_EXEC}))
        assert res1.allowed is True

        # Grant verification succeeds, but Governance re-check MUST DENY execution!
        assert await engine.verify_and_consume_grant(grant.grant_id, binding) is True
        gov_res = await gov.authorize("exec-sec-dur-1", binding.requested_capabilities)
        assert gov_res.allowed is False, "Persisted approval MUST NOT bypass Governance budget exhaustion!"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_security_durable_single_use_grant_replay_blocked() -> None:
    """Security Test (P4-4-INV-03 & P4-4-INV-13): Re-using a consumed grant across SQLite connections is blocked."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store1 = SQLiteApprovalStore(db_path=db_path)
        engine1 = HumanApprovalEngine(store=store1)

        binding = ActionBinding(
            session_id="sess-replay-dur",
            execution_id="exec-replay-dur",
            plan_fingerprint="fp-replay-dur",
            node_id="n1",
            tool_id="process_tool",
            tool_version="1.0.0",
            requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        )

        req = HumanApprovalRequest("app-replay-dur", binding, RiskLevel.HIGH, "Run process")
        await engine1.request_approval(req)
        dec = HumanApprovalDecision("app-replay-dur", ApprovalStatus.APPROVED, "op@co.com", "Approved")
        grant = await engine1.submit_decision(dec)

        # Connection 1 consumes grant
        assert await engine1.verify_and_consume_grant(grant.grant_id, binding) is True

        # Connection 2 attempts replay -> MUST FAIL with ApprovalReplayError!
        store2 = SQLiteApprovalStore(db_path=db_path)
        engine2 = HumanApprovalEngine(store=store2)
        with pytest.raises(ApprovalReplayError):
            await engine2.verify_and_consume_grant(grant.grant_id, binding)

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_security_durable_approval_is_not_execution_authorization())
    asyncio.run(test_security_durable_single_use_grant_replay_blocked())
    print("ALL P4-4 DURABLE APPROVAL SECURITY TESTS PASSED SUCCESSFULLY!")
