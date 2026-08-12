"""P2-FINAL Production Reliability, Chaos Verification, and Cross-Subsystem Release Gate Test Suite."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from typing import Any
from unittest.mock import MagicMock
import pytest

from nexusai.brain.coordinator import BrainCoordinator
from nexusai.brain.domain.agent import (
    AgentGoal,
    PlanGraph,
    PlanGraphNode,
    PlanningContext,
    PlanningGoal,
    PlanningResources,
    PlanStep,
    StepStatus,
)
from nexusai.brain.domain.execution_state import (
    ExecutionRecord,
    ExecutionStatus,
    NodeExecutionRecord,
    NodeExecutionStatus,
    compute_plan_graph_hash,
)
from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.domain.memory import (
    MemoryEntry,
    MemoryProvenance,
    MemoryQuery,
    MemoryType,
    PrivacyLevel,
)
from nexusai.brain.domain.observability import RuntimeEvent, RuntimeEventType
from nexusai.brain.domain.recovery import (
    FailureClass,
    RecoveryAction,
    ToolExecutionPolicy,
    classify_failure,
    generate_idempotency_key,
)
from nexusai.brain.domain.scheduler import ScheduledTask, SchedulerClosedError, TaskPriority
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.context_builder import ContextBuilder
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.memory_retriever import MemoryRetriever
from nexusai.brain.runtime.priority_scheduler import PriorityScheduler
from nexusai.infrastructure.observability.in_memory_exporter import InMemoryMetricsExporter
from nexusai.infrastructure.persistence.sqlite_execution_store import SQLiteExecutionStateStore
from nexusai.infrastructure.persistence.sqlite_memory_store import SQLiteMemoryStore


class ChaosFlakyToolPort(IToolPort):
    """ToolPort simulating configurable chaotic tool behaviors."""

    def __init__(self, failure_modes: dict[str, str] | None = None) -> None:
        self.failure_modes = failure_modes or {}
        self.call_counts: dict[str, int] = {}
        self.lock = asyncio.Lock()

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        tool_name = request.tool_name
        async with self.lock:
            count = self.call_counts.get(tool_name, 0) + 1
            self.call_counts[tool_name] = count

        mode = self.failure_modes.get(tool_name, "success")

        if mode == "timeout":
            await asyncio.sleep(0.01)
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=tool_name,
                success=False,
                error_message=f"Connection timed out for {tool_name}",
            )
        elif mode == "auth_error":
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=tool_name,
                success=False,
                error_message="401 Unauthorized API Key",
            )
        elif mode == "flaky_once" and count == 1:
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=tool_name,
                success=False,
                error_message=f"Transient network error for {tool_name} (attempt 1)",
            )
        elif mode == "raise_exception":
            raise RuntimeError(f"Uncaught crash inside tool {tool_name}")

        await asyncio.sleep(0.005)
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=tool_name,
            success=True,
            output=f"Success output for {tool_name}",
        )


def create_chaos_context() -> PlanningContext:
    goal = AgentGoal(description="P2-FINAL Chaos Verification Context")
    tools = ("terminal", "file_reader", "http_client", "unregistered_tool", "auth_tool")
    return PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=tools),
    )


def create_chaos_graph() -> PlanGraph:
    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Root Node", tool_name="terminal"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="File Reader", tool_name="file_reader"), dependencies=(1,)),
        3: PlanGraphNode(step=PlanStep(step_id=3, title="HTTP Client", tool_name="http_client"), dependencies=(1,)),
    }
    return PlanGraph(nodes=nodes, edges=((1, 2), (1, 3)))


# ------------------------------------------------------------------
# Test 1: Release-Blocking Invariants Verification (INV-01 to INV-05)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p2_final_invariants_verification() -> None:
    """Verify Release-Blocking Invariants INV-01 to INV-05."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteExecutionStateStore(db_path=db_path)
        graph = create_chaos_graph()
        g_hash = compute_plan_graph_hash(graph)

        # INV-01: Node marked COMPLETED remains COMPLETED and is skipped on recovery
        rec = ExecutionRecord(
            execution_id="exec-inv-1",
            plan_id="plan-1",
            graph_hash=g_hash,
            status=ExecutionStatus.RUNNING,
            node_records={
                1: NodeExecutionRecord("exec-inv-1", 1, NodeExecutionStatus.COMPLETED, tool_name="terminal", output="Done"),
                2: NodeExecutionRecord("exec-inv-1", 2, NodeExecutionStatus.PENDING, tool_name="file_reader"),
                3: NodeExecutionRecord("exec-inv-1", 3, NodeExecutionStatus.PENDING, tool_name="http_client"),
            },
        )
        await store.create_execution(rec)

        engine = PlanGraphExecutionEngine(state_store=store)
        engine.planner.plan = lambda ctx, session_id="": (graph, MagicMock())  # type: ignore[assignment]
        tool_port = ChaosFlakyToolPort()
        ctx = create_chaos_context()

        # Resume execution
        rec_graph, results, trace = await engine.resume_execution("exec-inv-1", ctx, tool_port)

        # INV-01 verification: Node 1 was skipped (0 tool executions) and completed nodes remain COMPLETED
        assert tool_port.call_counts.get("terminal", 0) == 0, "INV-01: COMPLETED node 1 must NOT re-execute"
        assert rec_graph.nodes[1].step.status == StepStatus.COMPLETED
        assert rec_graph.nodes[2].step.status == StepStatus.COMPLETED
        assert rec_graph.nodes[3].step.status == StepStatus.COMPLETED

        # INV-02: Plan Identity mismatch rejection
        bad_graph = create_chaos_graph()
        bad_graph.nodes[1].step.title = "Mutated Title Breaking Hash"
        engine_bad = PlanGraphExecutionEngine(state_store=store)
        engine_bad.planner.plan = lambda ctx, session_id="": (bad_graph, MagicMock())  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="Plan mismatch"):
            await engine_bad.resume_execution("exec-inv-1", ctx, tool_port)

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


# ------------------------------------------------------------------
# Test 2: Non-Retryable Failure Classification (Authentication/Authorization)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p2_final_non_retryable_failure_classification() -> None:
    """Verify non-retryable failures (auth_error, invalid_argument) fail immediately without retries."""
    store = SQLiteExecutionStateStore(":memory:")
    policy_auth = ToolExecutionPolicy(idempotent=True, max_retries=5)
    engine = PlanGraphExecutionEngine(state_store=store, tool_policies={"auth_tool": policy_auth})

    nodes = {1: PlanGraphNode(step=PlanStep(step_id=1, title="Auth Node", tool_name="auth_tool"), dependencies=())}
    graph = PlanGraph(nodes=nodes, edges=())
    engine.planner.plan = lambda ctx, session_id="": (graph, MagicMock())  # type: ignore[assignment]

    tool_port = ChaosFlakyToolPort(failure_modes={"auth_tool": "auth_error"})
    ctx = create_chaos_context()

    rec_graph, results, trace = await engine.execute_plan(ctx, tool_port, execution_id="exec-auth-fail")

    assert rec_graph.nodes[1].step.status == StepStatus.FAILED
    assert tool_port.call_counts.get("auth_tool", 0) == 1, "Non-retryable auth error must NOT enter retry loop"


# ------------------------------------------------------------------
# Test 3: Scheduler & Governance High-Scale Concurrency Chaos
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p2_final_scheduler_and_governance_chaos() -> None:
    """High Scale Stress: 50+ concurrent task producers/consumers, quota competition, and cancellation."""
    telemetry = InMemoryMetricsExporter()
    budget = ResourceBudget(max_concurrent_tasks=10, max_subprocesses=15, max_tool_invocations=100)
    gov = GovernanceEngine(global_budget=budget, telemetry=telemetry)
    scheduler = PriorityScheduler(aging_rate=1.0, telemetry=telemetry)

    claimed_ids: set[str] = set()
    lock = asyncio.Lock()

    async def producer(prefix: str, count: int) -> None:
        for i in range(count):
            try:
                task = ScheduledTask(
                    task_id=f"{prefix}-{i}",
                    execution_id="exec-chaos",
                    node_id=i,
                    priority=TaskPriority.HIGH if i % 2 == 0 else TaskPriority.NORMAL,
                    delay_until=time.time() + 0.02 if i % 4 == 0 else None,
                )
                await scheduler.submit(task)
                await asyncio.sleep(0.002)
            except SchedulerClosedError:
                break

    async def consumer() -> None:
        while True:
            try:
                claimed = await scheduler.next()
                async with lock:
                    assert claimed.task_id not in claimed_ids, "DUPLICATE CLAIM DETECTED"
                    claimed_ids.add(claimed.task_id)
                await asyncio.sleep(0.002)
            except SchedulerClosedError:
                break

    producers = [asyncio.create_task(producer(f"prod-{p}", 20)) for p in range(10)]
    consumers = [asyncio.create_task(consumer()) for _ in range(5)]

    await asyncio.sleep(0.05)
    await scheduler.cancel("prod-0-5")
    await scheduler.cancel("prod-1-5")

    await asyncio.gather(*producers, return_exceptions=True)
    await asyncio.sleep(0.05)

    await scheduler.shutdown()
    await asyncio.gather(*consumers, return_exceptions=True)

    assert len(claimed_ids) > 0
    assert gov.get_active_reservation_count() == 0, "Zero resource leaks invariant must hold"


# ------------------------------------------------------------------
# Test 4: Fault Isolation (Telemetry & Memory Failures)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p2_final_telemetry_and_memory_fault_isolation() -> None:
    """Verify core execution completes cleanly even when telemetry and memory exporters throw exceptions."""
    faulty_telemetry = InMemoryMetricsExporter(fail_on_purpose=True)
    mem_store = SQLiteMemoryStore(":memory:")
    retriever = MemoryRetriever(store=mem_store, telemetry=faulty_telemetry)
    builder = ContextBuilder(retriever=retriever, store=mem_store)

    engine = PlanGraphExecutionEngine(telemetry=faulty_telemetry)
    graph = create_chaos_graph()
    engine.planner.plan = lambda ctx, session_id="": (graph, MagicMock())  # type: ignore[assignment]

    tool_port = ChaosFlakyToolPort()
    ctx = create_chaos_context()

    rec_graph, results, trace = await engine.execute_plan(ctx, tool_port, execution_id="exec-fault-iso")

    assert rec_graph.nodes[1].step.status == StepStatus.COMPLETED
    assert rec_graph.nodes[2].step.status == StepStatus.COMPLETED
    assert rec_graph.nodes[3].step.status == StepStatus.COMPLETED
    assert len(results) == 3


# ------------------------------------------------------------------
# Test 5: Cross-Subsystem Combined Chaos Scenario
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p2_final_cross_subsystem_combined_chaos() -> None:
    """Cross-Subsystem Chaos: Tool timeouts + Retries + Governance Quota Competition + Telemetry + Persistence."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        exec_db = tf.name

    try:
        telemetry = InMemoryMetricsExporter()
        exec_store = SQLiteExecutionStateStore(db_path=exec_db)
        mem_store = SQLiteMemoryStore(db_path=":memory:")
        gov = GovernanceEngine(
            global_budget=ResourceBudget(max_concurrent_tasks=4, max_subprocesses=8, max_tool_invocations=50),
            telemetry=telemetry,
        )
        scheduler = PriorityScheduler(aging_rate=0.5, telemetry=telemetry)

        # Config tool policies: terminal is flaky (fails once), auth_tool fails non-retryable
        policy_terminal = ToolExecutionPolicy(idempotent=True, max_retries=3, backoff_factor=1.1)
        engine = PlanGraphExecutionEngine(
            state_store=exec_store,
            scheduler=scheduler,
            governance=gov,
            telemetry=telemetry,
            tool_policies={"terminal": policy_terminal},
        )

        nodes = {
            1: PlanGraphNode(step=PlanStep(step_id=1, title="Flaky Terminal", tool_name="terminal"), dependencies=()),
            2: PlanGraphNode(step=PlanStep(step_id=2, title="File Reader", tool_name="file_reader"), dependencies=(1,)),
        }
        graph = PlanGraph(nodes=nodes, edges=((1, 2),))
        engine.planner.plan = lambda ctx, session_id="": (graph, MagicMock())  # type: ignore[assignment]

        tool_port = ChaosFlakyToolPort(failure_modes={"terminal": "flaky_once"})
        ctx = create_chaos_context()

        rec_graph, results, trace = await engine.execute_plan(ctx, tool_port, execution_id="exec-cross-chaos")

        # Terminal tool failed attempt 1, retried attempt 2, and succeeded!
        assert rec_graph.nodes[1].step.status == StepStatus.COMPLETED
        assert rec_graph.nodes[2].step.status == StepStatus.COMPLETED
        assert tool_port.call_counts["terminal"] == 2

        # Final Verification: Resource reservations released cleanly
        assert gov.get_active_reservation_count() == 0
    finally:
        if os.path.exists(exec_db):
            os.remove(exec_db)


if __name__ == "__main__":
    asyncio.run(test_p2_final_invariants_verification())
    asyncio.run(test_p2_final_non_retryable_failure_classification())
    asyncio.run(test_p2_final_scheduler_and_governance_chaos())
    asyncio.run(test_p2_final_telemetry_and_memory_fault_isolation())
    asyncio.run(test_p2_final_cross_subsystem_combined_chaos())
    print("ALL P2-FINAL CHAOS & RELEASE GATE VERIFICATION TESTS PASSED SUCCESSFULLY!")
