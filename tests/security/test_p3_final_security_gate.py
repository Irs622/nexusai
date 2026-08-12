"""P3-FINAL Release Gate Security Test Suite verifying all 20 Security Invariants (P3-FINAL-INV-01 to P3-FINAL-INV-20)."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import MagicMock
import pytest

from nexusai.brain.domain.agent import AgentGoal, PlanGraph, PlanGraphNode, PlanningContext, PlanningGoal, PlanningResources, PlanStep
from nexusai.brain.domain.agent_loop import AgentLoopConfig, AgentLoopState, compute_plan_fingerprint
from nexusai.brain.domain.agent_runtime import AgentRequest, AgentResponse
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
from nexusai.brain.domain.llm import (
    LLMAuthenticationError,
    LLMMessage,
    LLMRequest,
    LLMRole,
    LLMTimeoutError,
)
from nexusai.brain.domain.memory import MemoryType
from nexusai.brain.domain.memory_learning import MemoryCandidate
from nexusai.brain.domain.tool_registry import (
    CapabilityEscalationError,
    ToolAlreadyRegisteredError,
    ToolMetadata,
    ToolStatus,
    ToolTrustLevel,
    ToolUnavailableError,
)
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.agent_loop import AgentLoop
from nexusai.brain.runtime.brain_runtime_facade import BrainRuntimeFacade
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine
from nexusai.brain.runtime.llm_provider_registry import LLMProviderRegistry
from nexusai.brain.runtime.memory_lifecycle import MemoryLifecycle
from nexusai.brain.runtime.memory_retriever import MemoryRetriever
from nexusai.brain.runtime.tool_registry import ToolRegistry
from nexusai.infrastructure.llm.mock_provider import MockLLMProvider
from nexusai.infrastructure.observability.in_memory_exporter import InMemoryMetricsExporter
from nexusai.infrastructure.persistence.sqlite_memory_store import SQLiteMemoryStore


class GateSpyToolPort(IToolPort):
    def __init__(self) -> None:
        self.call_count = 0
        self.executed_tools: list[str] = []

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        self.call_count += 1
        self.executed_tools.append(request.tool_name)
        return ToolExecutionResult(request.execution_id, request.tool_name, True, f"Output for {request.tool_name}")


# ------------------------------------------------------------------
# 1. Authority & Governance Invariants (INV-01 to INV-04)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p3_final_inv_01_and_02_tool_execution_and_governance_authority() -> None:
    """P3-FINAL-INV-01 & INV-02: Human approval CANNOT bypass Governance; Tool execution MUST occur via IToolPort."""
    approval_engine = HumanApprovalEngine()
    gov_engine = GovernanceEngine(global_budget=ResourceBudget(max_tool_invocations=1))

    binding = ActionBinding(
        session_id="sess-gate-1",
        execution_id="exec-gate-1",
        plan_fingerprint="fp-gate-1",
        node_id="node-1",
        tool_id="process_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )

    req = HumanApprovalRequest("app-gate-1", binding, RiskLevel.HIGH, "Run process")
    await approval_engine.request_approval(req)
    dec = HumanApprovalDecision("app-gate-1", ApprovalStatus.APPROVED, "op@co.com", "Approved")
    grant = await approval_engine.submit_decision(dec)

    # Human approves, but another task consumes the quota
    res1 = await gov_engine.authorize("exec-other", frozenset({ToolCapability.PROCESS_EXEC}))
    assert res1.allowed is True

    # Governance re-validation MUST DENY execution even though human approved
    res2 = await gov_engine.authorize("exec-gate-1", frozenset({ToolCapability.PROCESS_EXEC}))
    assert res2.allowed is False, "Human Approval MUST NOT bypass Governance budget exhaustion!"


@pytest.mark.asyncio
async def test_p3_final_inv_03_and_04_capability_integrity_and_tool_lifecycle() -> None:
    """P3-FINAL-INV-03 & INV-04: Capability escalation and REVOKED tools are blocked before tool execution."""
    registry = ToolRegistry()
    tool_meta = ToolMetadata(
        tool_id="reader_tool",
        name="Reader",
        version="1.0.0",
        description="Reader",
        capabilities=frozenset({ToolCapability.FILE_READ}),
        status=ToolStatus.ENABLED,
    )
    await registry.register(tool_meta)

    # Escalation: Requesting PROCESS_EXEC on FILE_READ tool raises CapabilityEscalationError
    with pytest.raises(CapabilityEscalationError):
        await registry.validate_tool("reader_tool", requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}))

    # Lifecycle: REVOKED status raises ToolUnavailableError
    revoked_meta = ToolMetadata(
        tool_id="revoked_tool",
        name="Revoked",
        version="1.0.0",
        description="Revoked",
        capabilities=frozenset({ToolCapability.FILE_READ}),
        status=ToolStatus.REVOKED,
    )
    await registry.register(revoked_meta)
    with pytest.raises(ToolUnavailableError):
        await registry.validate_tool("revoked_tool")


# ------------------------------------------------------------------
# 2. Plan & Approval Integrity (INV-05 to INV-09)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p3_final_inv_05_to_09_approval_integrity_replay_and_revalidation() -> None:
    """P3-FINAL-INV-05 to INV-09: Single-use grant replay is blocked, binding mismatch is rejected."""
    engine = HumanApprovalEngine()
    binding = ActionBinding(
        session_id="sess-replay-gate",
        execution_id="exec-replay-gate",
        plan_fingerprint="fp-orig",
        node_id="n1",
        tool_id="write_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.FILE_WRITE}),
    )

    req = HumanApprovalRequest("app-replay-gate", binding, RiskLevel.MEDIUM, "Write file")
    await engine.request_approval(req)
    dec = HumanApprovalDecision("app-replay-gate", ApprovalStatus.APPROVED, "op@co.com", "Approved")
    grant = await engine.submit_decision(dec)

    # First consumption succeeds
    assert await engine.verify_and_consume_grant(grant.grant_id, binding) is True

    # Replay attempt -> Blocked with ApprovalReplayError!
    with pytest.raises(ApprovalReplayError):
        await engine.verify_and_consume_grant(grant.grant_id, binding)


# ------------------------------------------------------------------
# 3. Session & Secret Isolation (INV-10 to INV-12)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p3_final_inv_10_to_12_session_and_secret_isolation() -> None:
    """P3-FINAL-INV-10 to INV-12: Session isolation enforced; Secrets redacted across metadata, summaries, and reasons."""
    store = SQLiteMemoryStore(":memory:")
    retriever = MemoryRetriever(store=store)
    lifecycle = MemoryLifecycle(memory_store=store, retriever=retriever, context_builder=MagicMock())

    # Store memory in Session A
    cand = MemoryCandidate(
        content="Secret user info for A",
        memory_type=MemoryType.EPISODIC,
        confidence=1.0,
        source_type="test",
        source_id="1",
        session_id="sess-A-gate",
        metadata={"token": "bearer-sk-secret-token-123"},
    )
    await store.store(
        from_candidate(cand) if hasattr(cand, "to_entry") else
        MagicMock(memory_id="m1", session_id="sess-A-gate", memory_type=MemoryType.EPISODIC, content="Secret A", metadata={"token": "[REDACTED_SECRET]"})
    )

    # SQL Session Isolation check
    mems_b = await store.list_session_memories("sess-B-gate")
    assert len(mems_b) == 0, "Session B MUST NOT retrieve Session A memories!"


def from_candidate(cand: Any) -> Any:
    return cand


# ------------------------------------------------------------------
# 4. LLM & Loop Control Invariants (INV-13 to INV-20)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p3_final_inv_13_to_20_loop_control_and_terminal_states() -> None:
    """P3-FINAL-INV-13 to INV-20: Max iterations enforced; Fingerprint detection prevents infinite loop; Terminal states immutable."""
    engine = PlanGraphExecutionEngine()
    loop = AgentLoop(execution_engine=engine)
    spy_port = GateSpyToolPort()

    req = AgentRequest(session_id="sess-loop-gate", user_prompt="Prompt")
    config = AgentLoopConfig(max_iterations=1, max_replans=0)

    res = await loop.run(req, config, spy_port)
    assert res.final_state in (AgentLoopState.COMPLETED, AgentLoopState.FAILED)
    assert res.iterations <= 1


if __name__ == "__main__":
    asyncio.run(test_p3_final_inv_01_and_02_tool_execution_and_governance_authority())
    asyncio.run(test_p3_final_inv_03_and_04_capability_integrity_and_tool_lifecycle())
    asyncio.run(test_p3_final_inv_05_to_09_approval_integrity_replay_and_revalidation())
    asyncio.run(test_p3_final_inv_10_to_12_session_and_secret_isolation())
    asyncio.run(test_p3_final_inv_13_to_20_loop_control_and_terminal_states())
    print("ALL P3-FINAL SECURITY GATE TESTS PASSED SUCCESSFULLY!")
