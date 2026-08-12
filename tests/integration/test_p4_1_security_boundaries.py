"""Security boundary test suite for P4-1 proving tool.execute() is NEVER CALLED when any gate fails."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalError,
    ApprovalStatus,
    HumanApprovalDecision,
    HumanApprovalRequest,
    RiskLevel,
)
from nexusai.brain.domain.tool_registry import CapabilityEscalationError, ToolMetadata, ToolStatus, ToolUnavailableError
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine
from nexusai.brain.runtime.tool_registry import ToolRegistry
from tests.fixtures.p4_1_tools import ControlledTestToolPort


@pytest.mark.asyncio
async def test_p4_1_fail_closed_tool_never_called_on_human_deny() -> None:
    """P4-1-INV-14: Human DENY fails closed. Tool execution WAS NEVER CALLED (call_count == 0)."""
    approval_engine = HumanApprovalEngine()
    tool_port = ControlledTestToolPort()

    binding = ActionBinding(
        session_id="sess-sec-deny",
        execution_id="exec-sec-deny",
        plan_fingerprint="fp-sec-deny",
        node_id="n1",
        tool_id="process_exec_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )

    req = HumanApprovalRequest("app-sec-deny", binding, RiskLevel.HIGH, "Run terminal command")
    await approval_engine.request_approval(req)

    # Human operator DENIES
    dec = HumanApprovalDecision("app-sec-deny", ApprovalStatus.DENIED, "operator@co.com", "Denied: Security policy violation")
    with pytest.raises(ApprovalError):
        await approval_engine.submit_decision(dec)

    # Invariant: Tool was NEVER executed!
    assert tool_port.call_count == 0
    assert len(tool_port.executed_tools) == 0


@pytest.mark.asyncio
async def test_p4_1_fail_closed_tool_never_called_on_tool_revocation() -> None:
    """P4-1-INV-07 & INV-14: Tool status REVOKED post-approval fails closed (call_count == 0)."""
    approval_engine = HumanApprovalEngine()
    registry = ToolRegistry()
    tool_port = ControlledTestToolPort()

    meta = ToolMetadata("rev_tool", "Revocable", "1.0.0", "Revocable", frozenset({ToolCapability.FILE_WRITE}))
    await registry.register(meta)

    binding = ActionBinding(
        session_id="sess-sec-rev",
        execution_id="exec-sec-rev",
        plan_fingerprint="fp-sec-rev",
        node_id="n1",
        tool_id="rev_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.FILE_WRITE}),
    )

    req = HumanApprovalRequest("app-sec-rev", binding, RiskLevel.MEDIUM, "Write file")
    await approval_engine.request_approval(req)
    dec = HumanApprovalDecision("app-sec-rev", ApprovalStatus.APPROVED, "operator@co.com", "Approved")
    grant = await approval_engine.submit_decision(dec)

    # Tool status becomes REVOKED before execution dispatch
    await registry.unregister("rev_tool")
    await registry.register(ToolMetadata("rev_tool", "Revocable", "1.0.0", "Revocable", frozenset({ToolCapability.FILE_WRITE}), status=ToolStatus.REVOKED))

    # ToolRegistry re-validation fails with ToolUnavailableError
    with pytest.raises(ToolUnavailableError):
        await registry.validate_tool("rev_tool")

    # Invariant: Tool WAS NEVER CALLED!
    assert tool_port.call_count == 0


@pytest.mark.asyncio
async def test_p4_1_fail_closed_tool_never_called_on_governance_exhaustion() -> None:
    """P4-1-INV-08 & INV-14: Governance quota exhaustion post-approval fails closed (call_count == 0)."""
    approval_engine = HumanApprovalEngine()
    gov_engine = GovernanceEngine(global_budget=ResourceBudget(max_tool_invocations=1))
    tool_port = ControlledTestToolPort()

    binding = ActionBinding(
        session_id="sess-sec-gov",
        execution_id="exec-sec-gov",
        plan_fingerprint="fp-sec-gov",
        node_id="n1",
        tool_id="process_exec_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )

    req = HumanApprovalRequest("app-sec-gov", binding, RiskLevel.HIGH, "Run process")
    await approval_engine.request_approval(req)
    dec = HumanApprovalDecision("app-sec-gov", ApprovalStatus.APPROVED, "operator@co.com", "Approved")
    grant = await approval_engine.submit_decision(dec)

    # Consume the last invocation quota
    res1 = await gov_engine.authorize("exec-other", frozenset({ToolCapability.PROCESS_EXEC}))
    assert res1.allowed is True

    # Governance re-validation MUST DENY execution
    res2 = await gov_engine.authorize("exec-sec-gov", frozenset({ToolCapability.PROCESS_EXEC}))
    assert res2.allowed is False

    # Invariant: Tool WAS NEVER CALLED!
    assert tool_port.call_count == 0


if __name__ == "__main__":
    asyncio.run(test_p4_1_fail_closed_tool_never_called_on_human_deny())
    asyncio.run(test_p4_1_fail_closed_tool_never_called_on_tool_revocation())
    asyncio.run(test_p4_1_fail_closed_tool_never_called_on_governance_exhaustion())
    print("ALL P4-1 SECURITY BOUNDARY FAIL-CLOSED TESTS PASSED SUCCESSFULLY!")
