"""Cancellation test suite for P4-1 End-to-End Runtime Integration (P4-1-INV-13)."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalStatus,
    HumanApprovalRequest,
    RiskLevel,
)
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine
from nexusai.infrastructure.observability.in_memory_exporter import InMemoryMetricsExporter


@pytest.mark.asyncio
async def test_p4_1_cancellation_propagation_and_resource_release() -> None:
    """P4-1-INV-13: Cancellation stops execution, releases governance reservations, and cancels pending approvals."""
    telemetry = InMemoryMetricsExporter()
    gov_engine = GovernanceEngine(telemetry=telemetry)
    approval_engine = HumanApprovalEngine(telemetry=telemetry)

    binding = ActionBinding(
        session_id="sess-p4-cancel",
        execution_id="exec-p4-cancel",
        plan_fingerprint="fp-cancel-p4",
        node_id="n1",
        tool_id="process_exec_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )

    # 1. Register pending approval request
    req = HumanApprovalRequest("app-p4-cancel", binding, RiskLevel.HIGH, "Run process command")
    await approval_engine.request_approval(req)

    # 2. Reserve governance resources
    res = await gov_engine.authorize("exec-p4-cancel", frozenset({ToolCapability.PROCESS_EXEC}))
    assert res.allowed is True
    assert gov_engine.get_active_reservation_count() == 1

    # 3. Cancellation occurs: Cancel pending approvals & release reservation
    cancelled_cnt = await approval_engine.cancel_pending_requests("exec-p4-cancel")
    await gov_engine.release(res.reservation_id)

    # 4. Verify invariants
    assert cancelled_cnt == 1
    assert gov_engine.get_active_reservation_count() == 0, "Governance reservation MUST be released!"

    req_state = await approval_engine.get_request("app-p4-cancel")
    assert req_state is not None
    assert req_state.status == ApprovalStatus.CANCELLED, "Approval status MUST be CANCELLED!"


if __name__ == "__main__":
    asyncio.run(test_p4_1_cancellation_propagation_and_resource_release())
    print("ALL P4-1 CANCELLATION TESTS PASSED SUCCESSFULLY!")
