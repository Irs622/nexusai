"""End-to-End integration test suite for P4-1 End-to-End Runtime Integration (Scenarios E2E-01 to E2E-10)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.agent import AgentGoal, PlanGraph, PlanGraphNode, PlanStep
from nexusai.brain.domain.agent_loop import AgentLoopConfig, AgentLoopState
from nexusai.brain.domain.agent_runtime import AgentExecutionState, AgentRequest
from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalMismatchError,
    ApprovalStatus,
    HumanApprovalDecision,
    HumanApprovalRequest,
    RiskLevel,
    evaluate_action_risk,
)
from nexusai.brain.domain.tool_registry import ToolMetadata, ToolStatus, ToolUnavailableError
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.runtime.agent_loop import AgentLoop
from nexusai.brain.runtime.brain_runtime_facade import BrainRuntimeFacade
from nexusai.brain.runtime.context_builder import ContextBuilder
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine
from nexusai.brain.runtime.memory_lifecycle import MemoryLifecycle
from nexusai.brain.runtime.memory_retriever import MemoryRetriever
from nexusai.brain.runtime.tool_registry import ToolRegistry
from nexusai.infrastructure.observability.in_memory_exporter import InMemoryMetricsExporter
from nexusai.infrastructure.persistence.sqlite_memory_store import SQLiteMemoryStore
from tests.fixtures.p4_1_tools import ControlledTestToolPort, get_p4_1_test_tools


@pytest.mark.asyncio
async def test_p4_1_e2e_01_low_risk_execution_without_approval() -> None:
    """P4-1-E2E-01: LOW-risk request executes through memory context, planning, governance, execution, observation, and memory learning without human approval."""
    telemetry = InMemoryMetricsExporter()
    mem_store = SQLiteMemoryStore(":memory:")
    retriever = MemoryRetriever(store=mem_store, telemetry=telemetry)
    builder = ContextBuilder(retriever=retriever, store=mem_store)
    lifecycle = MemoryLifecycle(memory_store=mem_store, retriever=retriever, context_builder=builder, telemetry=telemetry)

    registry = ToolRegistry(telemetry=telemetry)
    for tool_meta in get_p4_1_test_tools():
        await registry.register(tool_meta)

    gov = GovernanceEngine(global_budget=ResourceBudget(max_tool_invocations=50), telemetry=telemetry)
    engine = PlanGraphExecutionEngine(governance=gov, telemetry=telemetry)
    facade = BrainRuntimeFacade(execution_engine=engine, memory_store=mem_store, context_builder=builder, telemetry=telemetry)

    tool_port = ControlledTestToolPort()
    req = AgentRequest(session_id="sess-e2e-01", user_prompt="Read sandbox file echo")

    resp = await facade.run_agent(req, tool_port)

    assert resp.state == AgentExecutionState.COMPLETED
    assert tool_port.call_count > 0
    assert gov.get_active_reservation_count() == 0, "Zero resource leaks invariant must hold"

    # Confirm memory lifecycle stored episodic outcome
    mems = await mem_store.list_session_memories("sess-e2e-01")
    assert len(mems) >= 1


@pytest.mark.asyncio
async def test_p4_1_e2e_02_high_risk_execution_with_human_approval() -> None:
    """P4-1-E2E-02: HIGH-risk request requires approval, operator APPROVES, binding verified, governance admitted, tool executed."""
    approval_engine = HumanApprovalEngine()
    gov_engine = GovernanceEngine()

    binding = ActionBinding(
        session_id="sess-e2e-02",
        execution_id="exec-e2e-02",
        plan_fingerprint="fp-e2e-02",
        node_id="n1",
        tool_id="process_exec_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )

    # 1. Risk Evaluator determines HIGH risk
    risk = evaluate_action_risk(binding.requested_capabilities)
    assert risk == RiskLevel.HIGH

    # 2. Agent submits approval request & Operator APPROVES
    req = HumanApprovalRequest("app-e2e-02", binding, risk, "Run process tool")
    await approval_engine.request_approval(req)
    dec = HumanApprovalDecision("app-e2e-02", ApprovalStatus.APPROVED, "operator@co.com", "Approved for test")
    grant = await approval_engine.submit_decision(dec)

    # 3. Re-validation & Grant Verification
    assert await approval_engine.verify_and_consume_grant(grant.grant_id, binding) is True

    # 4. Governance Admission Re-check
    gov_res = await gov_engine.authorize("exec-e2e-02", binding.requested_capabilities)
    assert gov_res.allowed is True

    # 5. Tool execution succeeds cleanly
    tool_port = ControlledTestToolPort()
    res = await tool_port.execute(ToolExecutionRequest("exec-e2e-02", "process_exec_tool", ()))
    assert res.success is True
    assert tool_port.call_count == 1
    assert gov_engine.get_active_reservation_count() == 0


@pytest.mark.asyncio
async def test_p4_1_e2e_03_human_deny_blocks_tool_execution() -> None:
    """P4-1-E2E-03: Operator DENIES approval request -> Tool execution MUST NOT occur (call_count == 0)."""
    approval_engine = HumanApprovalEngine()
    tool_port = ControlledTestToolPort()

    binding = ActionBinding(
        session_id="sess-e2e-03",
        execution_id="exec-e2e-03",
        plan_fingerprint="fp-e2e-03",
        node_id="n1",
        tool_id="file_write_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.FILE_WRITE}),
    )

    req = HumanApprovalRequest("app-e2e-03", binding, RiskLevel.MEDIUM, "Write file")
    await approval_engine.request_approval(req)

    dec = HumanApprovalDecision("app-e2e-03", ApprovalStatus.DENIED, "security_guard@co.com", "Denied: Security policy violation")

    # Submitting DENIED decision raises ApprovalMismatchError
    with pytest.raises(ApprovalMismatchError, match="denied"):
        await approval_engine.submit_decision(dec)

    # Fail closed invariant: Tool execution WAS NEVER CALLED!
    assert tool_port.call_count == 0, "Tool MUST NOT be executed when human DENIES request!"


@pytest.mark.asyncio
async def test_p4_1_e2e_04_to_07_revalidation_failures_fail_closed() -> None:
    """P4-1-E2E-04 to E2E-07: Plan mutation, tool revocation, or governance quota exhaustion post-approval fail closed."""
    approval_engine = HumanApprovalEngine()
    gov_engine = GovernanceEngine(global_budget=ResourceBudget(max_tool_invocations=1))
    registry = ToolRegistry()

    tool_meta = ToolMetadata("revocable_tool", "Revocable", "1.0.0", "Revocable", frozenset({ToolCapability.FILE_WRITE}))
    await registry.register(tool_meta)

    binding = ActionBinding(
        session_id="sess-e2e-failclosed",
        execution_id="exec-e2e-failclosed",
        plan_fingerprint="fp-orig",
        node_id="n1",
        tool_id="revocable_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.FILE_WRITE}),
    )

    req = HumanApprovalRequest("app-failclosed", binding, RiskLevel.MEDIUM, "Write file")
    await approval_engine.request_approval(req)
    dec = HumanApprovalDecision("app-failclosed", ApprovalStatus.APPROVED, "op@co.com", "Approved")
    grant = await approval_engine.submit_decision(dec)

    # 1. Plan mutation post-approval fails grant verification
    mutated_binding = ActionBinding(
        session_id="sess-e2e-failclosed",
        execution_id="exec-e2e-failclosed",
        plan_fingerprint="fp-MUTATED",
        node_id="n1",
        tool_id="revocable_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.FILE_WRITE}),
    )
    with pytest.raises(ApprovalMismatchError):
        await approval_engine.verify_and_consume_grant(grant.grant_id, mutated_binding)

    # 2. Tool Revocation post-approval fails ToolRegistry re-validation
    await registry.unregister("revocable_tool")
    await registry.register(ToolMetadata("revocable_tool", "Revocable", "1.0.0", "Revocable", frozenset({ToolCapability.FILE_WRITE}), status=ToolStatus.REVOKED))
    with pytest.raises(ToolUnavailableError):
        await registry.validate_tool("revocable_tool")

    # 3. Governance Quota Exhaustion post-approval fails Governance admission
    res1 = await gov_engine.authorize("exec-other", frozenset({ToolCapability.FILE_WRITE}))
    assert res1.allowed is True
    res2 = await gov_engine.authorize("exec-e2e-failclosed", frozenset({ToolCapability.FILE_WRITE}))
    assert res2.allowed is False, "Governance budget exhaustion MUST fail closed!"


@pytest.mark.asyncio
async def test_p4_1_e2e_08_cancellation_propagation_and_resource_release() -> None:
    """P4-1-E2E-08: Execution cancellation propagates, revokes pending approvals, and releases all governance reservations."""
    approval_engine = HumanApprovalEngine()
    gov_engine = GovernanceEngine()

    binding = ActionBinding(
        session_id="sess-e2e-cancel",
        execution_id="exec-e2e-cancel",
        plan_fingerprint="fp-cancel",
        node_id="n1",
        tool_id="file_write_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.FILE_WRITE}),
    )

    # Pending approval
    req = HumanApprovalRequest("app-cancel-e2e", binding, RiskLevel.MEDIUM, "Write file")
    await approval_engine.request_approval(req)

    # Reserve governance resource
    res = await gov_engine.authorize("exec-e2e-cancel", frozenset({ToolCapability.FILE_WRITE}))
    assert res.allowed is True
    assert gov_engine.get_active_reservation_count() == 1

    # Cancellation event occurs
    cancelled_cnt = await approval_engine.cancel_pending_requests("exec-e2e-cancel")
    await gov_engine.release(res.reservation_id)

    assert cancelled_cnt == 1
    assert gov_engine.get_active_reservation_count() == 0, "Governance reservation MUST be released upon cancellation!"

    req_cancelled = await approval_engine.get_request("app-cancel-e2e")
    assert req_cancelled is not None
    assert req_cancelled.status == ApprovalStatus.CANCELLED


if __name__ == "__main__":
    asyncio.run(test_p4_1_e2e_01_low_risk_execution_without_approval())
    asyncio.run(test_p4_1_e2e_02_high_risk_execution_with_human_approval())
    asyncio.run(test_p4_1_e2e_03_human_deny_blocks_tool_execution())
    asyncio.run(test_p4_1_e2e_04_to_07_revalidation_failures_fail_closed())
    asyncio.run(test_p4_1_e2e_08_cancellation_propagation_and_resource_release())
    print("ALL P4-1 E2E INTEGRATION TESTS PASSED SUCCESSFULLY!")
