"""Integration test suite for P2-2 Failure Recovery Policy, Retry, Idempotency, and Side-Effect Reconciliation."""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any
from unittest.mock import MagicMock
import pytest
from pydantic import BaseModel, Field

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
from nexusai.brain.domain.recovery import (
    FailureClass,
    RecoveryAction,
    RecoveryPolicyEngine,
    ToolExecutionPolicy,
    generate_idempotency_key,
)
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.reconciliation_port import DefaultReconciliationAdapter
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.infrastructure.persistence.sqlite_execution_store import SQLiteExecutionStateStore


class FlakyToolPort(IToolPort):
    """ToolPort simulating flaky and side-effecting tool behaviors."""

    def __init__(self, fail_until_attempt: dict[str, int] | None = None) -> None:
        self.fail_until_attempt = fail_until_attempt or {}
        self.attempts: dict[str, int] = {}
        self.executed_calls: list[str] = []

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        tool_name = request.tool_name
        self.executed_calls.append(tool_name)
        current = self.attempts.get(tool_name, 0) + 1
        self.attempts[tool_name] = current

        threshold = self.fail_until_attempt.get(tool_name, 0)
        if current <= threshold:
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=tool_name,
                success=False,
                error_message=f"Connection timed out for '{tool_name}' (attempt {current})",
            )
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=tool_name,
            success=True,
            output=f"Success output for {tool_name}",
        )


def create_15_node_context() -> PlanningContext:
    goal = AgentGoal(description="15-Node Recovery Integration Context")
    tools = tuple(f"tool_{i}" for i in range(1, 16))
    return PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=tools),
    )


def create_15_node_graph() -> PlanGraph:
    nodes = {}
    edges = []
    for i in range(1, 16):
        deps = (i - 1,) if i > 1 else ()
        nodes[i] = PlanGraphNode(
            step=PlanStep(step_id=i, title=f"Step {i}", tool_name=f"tool_{i}"),
            dependencies=deps,
        )
        if i > 1:
            edges.append((i - 1, i))
    return PlanGraph(nodes=nodes, edges=tuple(edges))


@pytest.mark.asyncio
async def test_L_retry_state_survives_process_restart() -> None:
    """Test L: Attempt count and retry state survive process restart in state store."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store1 = SQLiteExecutionStateStore(db_path=db_path)
        graph = create_15_node_graph()
        g_hash = compute_plan_graph_hash(graph)

        # Pre-seed DB with node 1 having attempt_count=2
        record = ExecutionRecord(
            execution_id="exec-retry-l",
            plan_id="plan-l",
            graph_hash=g_hash,
            status=ExecutionStatus.RUNNING,
            node_records={
                1: NodeExecutionRecord(
                    execution_id="exec-retry-l",
                    node_id=1,
                    status=NodeExecutionStatus.RETRY_WAIT,
                    tool_name="tool_1",
                    attempt_count=2,
                )
            },
        )
        await store1.create_execution(record)

        # Process restart: fresh engine instance
        store2 = SQLiteExecutionStateStore(db_path=db_path)
        policy_tool1 = ToolExecutionPolicy(idempotent=True, max_retries=3, backoff_factor=1.1)
        engine2 = PlanGraphExecutionEngine(state_store=store2, tool_policies={"tool_1": policy_tool1})
        engine2.planner.plan = lambda ctx, session_id="": (graph, MagicMock())  # type: ignore[assignment]

        flaky_port = FlakyToolPort(fail_until_attempt={"tool_1": 2})
        ctx = create_15_node_context()

        # Resume execution
        rec_graph, results, trace = await engine2.resume_execution(
            execution_id="exec-retry-l",
            ctx=ctx,
            tool_port=flaky_port,
            session_id="plan-l",
        )

        final_record = await store2.load_execution("exec-retry-l")
        assert final_record is not None
        # Attempt count resumed from 2, executed attempt 3 which succeeded
        assert final_record.node_records[1].attempt_count == 3
        assert final_record.node_records[1].status == NodeExecutionStatus.COMPLETED
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_P_15_node_dag_with_mixed_retry_and_reconciliation() -> None:
    """Test P: 15-node DAG executing mixed idempotent retries and non-idempotent reconciliation."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteExecutionStateStore(db_path=db_path)
        graph = create_15_node_graph()

        # Tool 4: Idempotent tool timing out once (will RETRY & succeed)
        policy_tool4 = ToolExecutionPolicy(idempotent=True, max_retries=3, backoff_factor=1.1)

        # Tool 5: Non-idempotent side-effecting tool timing out once (will RECONCILE & succeed via Reconciler)
        policy_tool5 = ToolExecutionPolicy(idempotent=False, side_effecting=True)

        idempotency_key_5 = generate_idempotency_key("exec-mixed-15", 5)
        reconciled_res = ToolExecutionResult(
            request_id="step-5",
            tool_name="tool_5",
            success=True,
            output="Reconciled external side effect success for tool_5",
        )
        reconciler = DefaultReconciliationAdapter(deterministic_outcomes={idempotency_key_5: reconciled_res})

        engine = PlanGraphExecutionEngine(
            state_store=store,
            reconciler=reconciler,
            tool_policies={"tool_4": policy_tool4, "tool_5": policy_tool5},
        )
        engine.planner.plan = lambda ctx, session_id="": (graph, MagicMock())  # type: ignore[assignment]

        flaky_port = FlakyToolPort(fail_until_attempt={"tool_4": 1, "tool_5": 1})
        ctx = create_15_node_context()

        rec_graph, results, trace = await engine.execute_plan(
            ctx=ctx,
            tool_port=flaky_port,
            session_id="session-p",
            execution_id="exec-mixed-15",
        )

        assert rec_graph.nodes[4].step.status == StepStatus.COMPLETED
        assert rec_graph.nodes[5].step.status == StepStatus.COMPLETED

        final_record = await store.load_execution("exec-mixed-15")
        assert final_record is not None
        assert final_record.node_records[4].attempt_count == 2, "Tool 4 must retry once"
        assert final_record.node_records[5].last_recovery_action == RecoveryAction.RECONCILE.value
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_Q_parent_cancellation_during_retry_backoff() -> None:
    """Test Q: Parent task cancellation while awaiting retry backoff delay propagates CancelledError cleanly."""
    store = SQLiteExecutionStateStore(":memory:")
    graph = create_15_node_graph()

    # Tool 1: Idempotent tool with long backoff delay (10s)
    policy_tool1 = ToolExecutionPolicy(idempotent=True, max_retries=3, max_backoff_seconds=10.0)
    engine = PlanGraphExecutionEngine(state_store=store, tool_policies={"tool_1": policy_tool1})
    engine.planner.plan = lambda ctx, session_id="": (graph, MagicMock())  # type: ignore[assignment]

    flaky_port = FlakyToolPort(fail_until_attempt={"tool_1": 5})
    ctx = create_15_node_context()

    task = asyncio.create_task(engine.execute_plan(ctx, flaky_port, execution_id="exec-cancel-q"))
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


def test_R_recovery_decision_determinism() -> None:
    """Test R: RecoveryPolicyEngine produces 100% deterministic decisions across repeated evaluations."""
    policy = ToolExecutionPolicy(idempotent=True, max_retries=3, backoff_factor=2.0)
    for _ in range(50):
        decision = RecoveryPolicyEngine.evaluate(policy, FailureClass.TIMEOUT, attempt_number=2, current_time=1000.0)
        assert decision.action == RecoveryAction.RETRY
        assert decision.retry_delay_seconds == 1.0
        assert decision.next_retry_at == 1001.0


if __name__ == "__main__":
    asyncio.run(test_L_retry_state_survives_process_restart())
    asyncio.run(test_P_15_node_dag_with_mixed_retry_and_reconciliation())
    asyncio.run(test_Q_parent_cancellation_during_retry_backoff())
    test_R_recovery_decision_determinism()
    print("ALL P2-2 RECOVERY INTEGRATION TESTS PASSED SUCCESSFULLY!")
