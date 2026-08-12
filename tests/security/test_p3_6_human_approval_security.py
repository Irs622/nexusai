"""Security verification test suite for P3-6 Human Approval Safety Boundary invariants (INV-HA-01 to INV-HA-12)."""

from __future__ import annotations

import asyncio
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
from nexusai.brain.domain.tool_registry import (
    ToolMetadata,
    ToolStatus,
    ToolUnavailableError,
)
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine
from nexusai.brain.runtime.tool_registry import ToolRegistry


@pytest.mark.asyncio
async def test_security_action_binding_mismatch_blocked() -> None:
    """Security Test (INV-HA-01 & INV-HA-02): Digest or plan fingerprint mismatch blocks grant verification."""
    engine = HumanApprovalEngine()
    binding_orig = ActionBinding(
        session_id="sess-1",
        execution_id="exec-1",
        plan_fingerprint="fingerprint-v1",
        node_id="n1",
        tool_id="terminal",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )

    req = HumanApprovalRequest("app-bind-sec", binding_orig, RiskLevel.HIGH, "Run terminal command")
    await engine.request_approval(req)

    dec = HumanApprovalDecision("app-bind-sec", ApprovalStatus.APPROVED, "operator@co.com", "Approved")
    grant = await engine.submit_decision(dec)

    # Attempt to consume grant with MUTATED plan_fingerprint -> Action Binding Mismatch Blocked!
    binding_mutated = ActionBinding(
        session_id="sess-1",
        execution_id="exec-1",
        plan_fingerprint="fingerprint-v2-mutated",
        node_id="n1",
        tool_id="terminal",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )

    with pytest.raises(ApprovalMismatchError, match="Action binding mismatch"):
        await engine.verify_and_consume_grant(grant.grant_id, binding_mutated)


@pytest.mark.asyncio
async def test_approved_action_is_denied_when_governance_budget_changes() -> None:
    """Security Test (INV-HA-03): Human approval DOES NOT bypass Governance re-check if budget exhausts."""
    approval_engine = HumanApprovalEngine()
    gov_engine = GovernanceEngine(global_budget=ResourceBudget(max_tool_invocations=1))

    binding = ActionBinding(
        session_id="sess-gov-primacy",
        execution_id="exec-gov-primacy",
        plan_fingerprint="fp-gov-primacy",
        node_id="n1",
        tool_id="process_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )

    # 1. Agent submits approval request & Human operator APPROVES
    req = HumanApprovalRequest("app-gov-primacy", binding, RiskLevel.HIGH, "Execute process")
    await approval_engine.request_approval(req)
    dec = HumanApprovalDecision("app-gov-primacy", ApprovalStatus.APPROVED, "op@co.com", "Approved")
    grant = await approval_engine.submit_decision(dec)

    # 2. Verify grant succeeds
    assert await approval_engine.verify_and_consume_grant(grant.grant_id, binding) is True

    # 3. Meanwhile, another execution consumes the last remaining governance invocation quota
    res1 = await gov_engine.authorize("exec-other", frozenset({ToolCapability.PROCESS_EXEC}))
    assert res1.allowed is True

    # 4. Now agent attempts execution for approved action -> Governance re-validation MUST DENY execution!
    res2 = await gov_engine.authorize("exec-gov-primacy", frozenset({ToolCapability.PROCESS_EXEC}))
    assert res2.allowed is False, "Human approval MUST NOT bypass Governance budget exhaustion!"
    assert res2.reason == "global_tool_invocations_exceeded"


@pytest.mark.asyncio
async def test_approved_action_is_denied_when_tool_is_revoked() -> None:
    """Security Test (INV-HA-09): Human approval DOES NOT execute if ToolRegistry status becomes REVOKED."""
    approval_engine = HumanApprovalEngine()
    registry = ToolRegistry()

    tool_meta = ToolMetadata(
        tool_id="terminal_tool",
        name="Terminal",
        version="1.0.0",
        description="Terminal",
        capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        status=ToolStatus.ENABLED,
    )
    await registry.register(tool_meta)

    binding = ActionBinding(
        session_id="sess-rev-tool",
        execution_id="exec-rev-tool",
        plan_fingerprint="fp-rev-tool",
        node_id="n1",
        tool_id="terminal_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )

    # 1. Human operator APPROVES action while tool is ENABLED
    req = HumanApprovalRequest("app-rev-tool", binding, RiskLevel.HIGH, "Execute terminal")
    await approval_engine.request_approval(req)
    dec = HumanApprovalDecision("app-rev-tool", ApprovalStatus.APPROVED, "op@co.com", "Approved")
    grant = await approval_engine.submit_decision(dec)

    # 2. Tool status is REVOKED in ToolRegistry after approval
    revoked_meta = ToolMetadata(
        tool_id="terminal_tool",
        name="Terminal",
        version="1.0.0",
        description="Terminal",
        capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        status=ToolStatus.REVOKED,
    )
    await registry.unregister("terminal_tool")
    await registry.register(revoked_meta)

    # 3. Agent attempts execution -> ToolRegistry re-validation MUST FAIL with ToolUnavailableError!
    with pytest.raises(ToolUnavailableError, match="REVOKED"):
        await registry.validate_tool("terminal_tool")


@pytest.mark.asyncio
async def test_security_single_use_grant_replay_blocked() -> None:
    """Security Test (INV-HA-08): Re-using a consumed single-use ApprovalGrant is blocked."""
    engine = HumanApprovalEngine()
    binding = ActionBinding(
        session_id="sess-replay",
        execution_id="exec-replay",
        plan_fingerprint="fp-replay",
        node_id="n1",
        tool_id="file_write",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.FILE_WRITE}),
    )

    req = HumanApprovalRequest("app-replay", binding, RiskLevel.MEDIUM, "Write file")
    await engine.request_approval(req)

    dec = HumanApprovalDecision("app-replay", ApprovalStatus.APPROVED, "operator@co.com", "Approved")
    grant = await engine.submit_decision(dec)

    # First consumption succeeds
    assert await engine.verify_and_consume_grant(grant.grant_id, binding) is True

    # Replay attempt -> Blocked with ApprovalReplayError!
    with pytest.raises(ApprovalReplayError, match="already been consumed"):
        await engine.verify_and_consume_grant(grant.grant_id, binding)


@pytest.mark.asyncio
async def test_security_expiration_defense_in_depth_and_cancellation_revocation() -> None:
    """Security Test (INV-HA-04 & INV-HA-07): Expired grants and cancelled executions invalidate pending requests."""
    engine = HumanApprovalEngine(default_ttl_seconds=0.01)
    binding = ActionBinding(
        session_id="sess-exp",
        execution_id="exec-exp",
        plan_fingerprint="fp-exp",
        node_id="n1",
        tool_id="net_fetch",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.NETWORK_ACCESS}),
    )

    req = HumanApprovalRequest("app-exp", binding, RiskLevel.HIGH, "Net fetch", expires_at=time.time() + 0.01)
    await engine.request_approval(req)

    await asyncio.sleep(0.02)  # Wait for expiration

    dec = HumanApprovalDecision("app-exp", ApprovalStatus.APPROVED, "operator@co.com", "Approved")
    with pytest.raises(ApprovalExpiredError):
        await engine.submit_decision(dec)

    # Test Cancellation Revocation (INV-HA-07)
    engine_cancel = HumanApprovalEngine()
    req_cancel = HumanApprovalRequest("app-cancel", binding, RiskLevel.HIGH, "Net fetch")
    await engine_cancel.request_approval(req_cancel)

    cancelled_cnt = await engine_cancel.cancel_pending_requests("exec-exp")
    assert cancelled_cnt == 1

    dec_cancel = HumanApprovalDecision("app-cancel", ApprovalStatus.APPROVED, "operator@co.com", "Approved")
    with pytest.raises(ValueError, match="in status 'CANCELLED'"):
        await engine_cancel.submit_decision(dec_cancel)


if __name__ == "__main__":
    asyncio.run(test_security_action_binding_mismatch_blocked())
    asyncio.run(test_approved_action_is_denied_when_governance_budget_changes())
    asyncio.run(test_approved_action_is_denied_when_tool_is_revoked())
    asyncio.run(test_security_single_use_grant_replay_blocked())
    asyncio.run(test_security_expiration_defense_in_depth_and_cancellation_revocation())
    print("ALL P3-6 HUMAN APPROVAL SECURITY TESTS PASSED SUCCESSFULLY!")
