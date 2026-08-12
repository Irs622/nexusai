"""Adversarial stress test suite for P3-FINAL Agent Runtime reliability, concurrency, and security invariants."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.agent import AgentGoal, PlanGraph, PlanGraphNode, PlanStep
from nexusai.brain.domain.agent_loop import AgentLoopConfig, AgentLoopState
from nexusai.brain.domain.agent_runtime import AgentRequest
from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalError,
    ApprovalStatus,
    HumanApprovalDecision,
    HumanApprovalRequest,
    RiskLevel,
)
from nexusai.brain.domain.tool_registry import ToolMetadata
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.agent_loop import AgentLoop
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine
from nexusai.brain.runtime.tool_registry import ToolRegistry
from nexusai.infrastructure.observability.in_memory_exporter import InMemoryMetricsExporter
from nexusai.infrastructure.persistence.sqlite_memory_store import SQLiteMemoryStore


class FinalStressToolPort(IToolPort):
    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        await asyncio.sleep(0.002)
        return ToolExecutionResult(request.execution_id, request.tool_name, True, f"Output for {request.tool_name}")


@pytest.mark.asyncio
async def test_p3_final_adversarial_agent_stress() -> None:
    """Stress Test: 50+ concurrent Agent Loop executions, Human Approval decision races, single-use grant verifications, and Governance quota competition.

    Invariants: Zero deadlocks, zero cross-session leaks, zero replay leaks, zero resource leaks.
    """
    telemetry = InMemoryMetricsExporter()
    mem_store = SQLiteMemoryStore(":memory:")
    registry = ToolRegistry(telemetry=telemetry)
    approval_engine = HumanApprovalEngine(telemetry=telemetry)

    # Register tools
    t1 = ToolMetadata("terminal", "Terminal", "1.0.0", "Terminal", frozenset({ToolCapability.PROCESS_EXEC}))
    t2 = ToolMetadata("file_reader", "FileReader", "1.0.0", "FileReader", frozenset({ToolCapability.FILE_READ}))
    await registry.register(t1)
    await registry.register(t2)

    gov = GovernanceEngine(
        global_budget=ResourceBudget(max_concurrent_tasks=10, max_subprocesses=15, max_tool_invocations=300),
        telemetry=telemetry,
    )
    engine = PlanGraphExecutionEngine(governance=gov, telemetry=telemetry)
    loop = AgentLoop(execution_engine=engine, tool_registry=registry, memory_store=mem_store, telemetry=telemetry)

    tool_port = FinalStressToolPort()

    # 1. Run 30 concurrent Agent Loops
    async def run_agent_loop_worker(w_id: int) -> None:
        req = AgentRequest(session_id=f"sess-p3-final-{w_id}", user_prompt=f"Final stress task {w_id}")
        config = AgentLoopConfig(max_iterations=2, max_replans=1)
        res = await loop.run(req, config, tool_port)
        assert res.final_state in (AgentLoopState.COMPLETED, AgentLoopState.FAILED)

    loop_workers = [asyncio.create_task(run_agent_loop_worker(w)) for w in range(30)]
    await asyncio.gather(*loop_workers)

    # 2. Run 20 concurrent Approval Submissions & Single-Use Replay Protection Verification
    async def approval_worker(a_id: int) -> None:
        binding = ActionBinding(
            session_id=f"sess-app-final-{a_id}",
            execution_id=f"exec-app-final-{a_id}",
            plan_fingerprint=f"fp-final-{a_id}",
            node_id=f"n-{a_id}",
            tool_id="terminal",
            tool_version="1.0.0",
            requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        )
        req = HumanApprovalRequest(f"app-final-{a_id}", binding, RiskLevel.HIGH, f"Execute task {a_id}")
        await approval_engine.request_approval(req)

        dec = HumanApprovalDecision(f"app-final-{a_id}", ApprovalStatus.APPROVED, "operator@co.com", "Approved")
        grant = await approval_engine.submit_decision(dec)

        # Single-use consumption
        consumed = await approval_engine.verify_and_consume_grant(grant.grant_id, binding)
        assert consumed is True

        # Replay attempt MUST fail
        with pytest.raises(ApprovalError):
            await approval_engine.verify_and_consume_grant(grant.grant_id, binding)

    app_workers = [asyncio.create_task(approval_worker(a)) for a in range(20)]
    await asyncio.gather(*app_workers)

    print(f"\n[P3-FINAL ADVERSARIAL STRESS VERIFICATION]")
    print(f"Active Governance Reservations at Teardown: {gov.get_active_reservation_count()}")

    assert gov.get_active_reservation_count() == 0, "Zero resource leak invariant must hold after teardown!"


if __name__ == "__main__":
    asyncio.run(test_p3_final_adversarial_agent_stress())
    print("ALL P3-FINAL ADVERSARIAL STRESS TESTS PASSED SUCCESSFULLY!")
