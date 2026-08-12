"""Integration and crash recovery test suite for P2-1 Execution State & Persistence."""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any
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
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.infrastructure.persistence.sqlite_execution_store import SQLiteExecutionStateStore


class SampleInputSchema(BaseModel):
    query: str = Field(default="test", description="Sample input")


class SpyToolPort(IToolPort):
    """ToolPort spy recording all tool executions."""

    def __init__(self) -> None:
        self.executed_tools: list[str] = []

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        self.executed_tools.append(request.tool_name)
        await asyncio.sleep(0.01)
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=request.tool_name,
            success=True,
            output=f"Output for {request.tool_name}",
        )


def create_15_node_context() -> PlanningContext:
    goal = AgentGoal(description="15-Node DAG Recovery Context")
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
async def test_full_15_node_crash_recovery() -> None:
    """Test realistic process crash recovery scenario:
    15-node DAG:
    Nodes 1-6: COMPLETED in DB
    Node 7: RUNNING in DB (crashed mid-execution)
    Nodes 8-15: PENDING in DB

    Restart fresh engine instance:
    - Nodes 1-6 are SKIPPED (not re-executed).
    - Node 7 is recovered from stale RUNNING state to PENDING and executed.
    - Nodes 8-15 execute cleanly.
    - Full DAG reaches COMPLETED state.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store1 = SQLiteExecutionStateStore(db_path=db_path)
        graph = create_15_node_graph()
        g_hash = compute_plan_graph_hash(graph)

        # Build initial DB state prior to crash simulation
        node_records = {}
        for i in range(1, 16):
            if 1 <= i <= 6:
                status = NodeExecutionStatus.COMPLETED
                output = f"Output for tool_{i}"
            elif i == 7:
                status = NodeExecutionStatus.RUNNING
                output = None
            else:
                status = NodeExecutionStatus.PENDING
                output = None

            node_records[i] = NodeExecutionRecord(
                execution_id="exec-crash-15",
                node_id=i,
                status=status,
                tool_name=f"tool_{i}",
                output=output,
            )

        exec_record = ExecutionRecord(
            execution_id="exec-crash-15",
            plan_id="session-crash",
            graph_hash=g_hash,
            status=ExecutionStatus.RUNNING,
            node_records=node_records,
        )
        await store1.create_execution(exec_record)

        # --- SIMULATE PROCESS TERMINATION / CRASH ---
        # Discard engine1 and store1 completely. Instantiate fresh engine2 & store2 from same DB!
        store2 = SQLiteExecutionStateStore(db_path=db_path)
        engine2 = PlanGraphExecutionEngine(state_store=store2)
        engine2.planner.plan = lambda ctx, session_id="": (graph, MagicMock())  # type: ignore[assignment]

        spy_port = SpyToolPort()
        ctx = create_15_node_context()

        # Resume execution
        recovered_graph, results, trace = await engine2.resume_execution(
            execution_id="exec-crash-15",
            ctx=ctx,
            tool_port=spy_port,
            session_id="session-crash",
        )

        # Assertions
        # 1. Nodes 1-6 were SKIPPED and NOT re-executed
        for i in range(1, 7):
            assert f"tool_{i}" not in spy_port.executed_tools, (
                f"Completed node tool_{i} must NOT be re-executed upon recovery!"
            )

        # 2. Node 7 and Nodes 8-15 WERE executed
        for i in range(7, 16):
            assert f"tool_{i}" in spy_port.executed_tools, (
                f"Uncompleted/recovered node tool_{i} must be executed!"
            )

        # 3. Final recovered graph status
        assert all(n.step.status == StepStatus.COMPLETED for n in recovered_graph.nodes.values())
        final_record = await store2.load_execution("exec-crash-15")
        assert final_record is not None
        assert final_record.status == ExecutionStatus.COMPLETED
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_plan_structural_hash_mismatch_rejection() -> None:
    """Test that attempting to resume an execution against an incompatible graph structure is rejected."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteExecutionStateStore(db_path=db_path)
        graph_orig = create_15_node_graph()
        g_hash_orig = compute_plan_graph_hash(graph_orig)

        record = ExecutionRecord(
            execution_id="exec-mismatch",
            plan_id="session-mismatch",
            graph_hash=g_hash_orig,
            status=ExecutionStatus.RUNNING,
        )
        await store.create_execution(record)

        # Create modified graph with different node title/structure
        nodes_mod = {
            1: PlanGraphNode(step=PlanStep(step_id=1, title="Step 1 MODIFIED", tool_name="tool_1"), dependencies=()),
        }
        graph_mod = PlanGraph(nodes=nodes_mod)

        engine = PlanGraphExecutionEngine(state_store=store)
        engine.planner.plan = lambda ctx, session_id="": (graph_mod, MagicMock())  # type: ignore[assignment]

        spy_port = SpyToolPort()
        ctx = create_15_node_context()

        with pytest.raises(RuntimeError, match="Plan mismatch"):
            await engine.resume_execution("exec-mismatch", ctx, spy_port)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    from unittest.mock import MagicMock
    asyncio.run(test_full_15_node_crash_recovery())
    asyncio.run(test_plan_structural_hash_mismatch_rejection())
    print("ALL P2-1 PERSISTENCE & CRASH RECOVERY INTEGRATION TESTS PASSED SUCCESSFULLY!")
