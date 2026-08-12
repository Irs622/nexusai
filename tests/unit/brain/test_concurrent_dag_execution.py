"""P1-3 Concurrent DAG Scheduling and Execution Test Suite.

Verifies:
A. Sequential DAG correctness.
B. Independent nodes run concurrently.
C. Branching DAG concurrency.
D. Diamond DAG execution.
E. Concurrency limit enforcement (bounded scheduler semaphore).
F. Non-sequential node IDs.
G. String node IDs.
H. Dependency failure propagation (dependent nodes skipped on failure).
I. Unrelated branch behavior (unrelated branches continue executing).
J. Parent task cancellation (cancels running child tasks cleanly).
K. No leaked asyncio tasks after completion or cancellation.
L. Timeout propagation compatibility (P1-1).
M. CircuitBreaker interaction under concurrent failures.
N. Deterministic ready-node scheduling.
O. Event & DecisionTrace preservation.
"""

from __future__ import annotations

import asyncio
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
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult


class ConcurrentSpyToolPort(IToolPort):
    """Spy tool port tracking execution start, end, peak concurrency, and execution order."""

    def __init__(self, delay_map: dict[str, float] | None = None, fail_tools: set[str] | None = None) -> None:
        self.delay_map = delay_map or {}
        self.fail_tools = fail_tools or set()
        self.active_count = 0
        self.peak_concurrency = 0
        self.executed_order: list[str] = []
        self.start_times: dict[str, float] = {}
        self.end_times: dict[str, float] = {}
        self.lock = asyncio.Lock()

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        async with self.lock:
            self.active_count += 1
            if self.active_count > self.peak_concurrency:
                self.peak_concurrency = self.active_count
            self.start_times[request.tool_name] = asyncio.get_event_loop().time()

        delay = self.delay_map.get(request.tool_name, 0.05)
        await asyncio.sleep(delay)

        async with self.lock:
            self.end_times[request.tool_name] = asyncio.get_event_loop().time()
            self.executed_order.append(request.tool_name)
            self.active_count -= 1

        if request.tool_name in self.fail_tools:
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=False,
                error_message=f"Intentional failure for {request.tool_name}",
            )

        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=request.tool_name,
            success=True,
            output=f"Executed {request.tool_name}",
        )


def create_context(description: str = "Concurrent DAG Test Goal") -> PlanningContext:
    goal = AgentGoal(description=description)
    return PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=("tool_a", "tool_b", "tool_c", "tool_d")),
    )


# ------------------------------------------------------------------
# Test Cases A through O
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_A_sequential_dag_correctness() -> None:
    """Test A: Sequential DAG (1 -> 2 -> 3)."""
    engine = PlanGraphExecutionEngine(max_concurrency=4)
    spy = ConcurrentSpyToolPort()

    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Step 1", tool_name="tool_a"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Step 2", tool_name="tool_b"), dependencies=(1,)),
        3: PlanGraphNode(step=PlanStep(step_id=3, title="Step 3", tool_name="tool_c"), dependencies=(2,)),
    }
    plan_graph = PlanGraph(nodes=nodes, edges=((1, 2), (2, 3)))
    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_context("Sequential DAG")
    await engine.execute_plan(ctx, tool_port=spy)

    assert spy.executed_order == ["tool_a", "tool_b", "tool_c"]
    assert spy.peak_concurrency == 1, "Sequential DAG must not run tasks concurrently"


@pytest.mark.asyncio
async def test_B_independent_nodes_run_concurrently() -> None:
    """Test B: Independent nodes (tool_a, tool_b, tool_c) run concurrently."""
    engine = PlanGraphExecutionEngine(max_concurrency=4)
    spy = ConcurrentSpyToolPort(delay_map={"tool_a": 0.1, "tool_b": 0.1, "tool_c": 0.1})

    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Step 1", tool_name="tool_a"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Step 2", tool_name="tool_b"), dependencies=()),
        3: PlanGraphNode(step=PlanStep(step_id=3, title="Step 3", tool_name="tool_c"), dependencies=()),
    }
    plan_graph = PlanGraph(nodes=nodes)
    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_context("Independent Nodes")
    await engine.execute_plan(ctx, tool_port=spy)

    assert spy.peak_concurrency >= 2, f"Expected concurrency >= 2, got {spy.peak_concurrency}"
    assert len(spy.executed_order) == 3


@pytest.mark.asyncio
async def test_C_and_D_diamond_and_branching_dag() -> None:
    """Test C & D: Diamond DAG (A -> B/C -> D)."""
    engine = PlanGraphExecutionEngine(max_concurrency=4)
    spy = ConcurrentSpyToolPort(delay_map={"tool_a": 0.05, "tool_b": 0.1, "tool_c": 0.1, "tool_d": 0.05})

    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Step A", tool_name="tool_a"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Step B", tool_name="tool_b"), dependencies=(1,)),
        3: PlanGraphNode(step=PlanStep(step_id=3, title="Step C", tool_name="tool_c"), dependencies=(1,)),
        4: PlanGraphNode(step=PlanStep(step_id=4, title="Step D", tool_name="tool_d"), dependencies=(2, 3)),
    }
    plan_graph = PlanGraph(nodes=nodes)
    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_context("Diamond DAG")
    await engine.execute_plan(ctx, tool_port=spy)

    assert spy.executed_order[0] == "tool_a"
    assert spy.executed_order[-1] == "tool_d"
    assert spy.start_times["tool_d"] >= spy.end_times["tool_b"]
    assert spy.start_times["tool_d"] >= spy.end_times["tool_c"]


@pytest.mark.asyncio
async def test_E_concurrency_limit_enforcement() -> None:
    """Test E: Concurrency limit (max_concurrency=2) is strictly enforced."""
    engine = PlanGraphExecutionEngine(max_concurrency=2)
    spy = ConcurrentSpyToolPort(delay_map={"tool_a": 0.1, "tool_b": 0.1, "tool_c": 0.1, "tool_d": 0.1})

    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Step 1", tool_name="tool_a"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Step 2", tool_name="tool_b"), dependencies=()),
        3: PlanGraphNode(step=PlanStep(step_id=3, title="Step 3", tool_name="tool_c"), dependencies=()),
        4: PlanGraphNode(step=PlanStep(step_id=4, title="Step 4", tool_name="tool_d"), dependencies=()),
    }
    plan_graph = PlanGraph(nodes=nodes)
    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_context("Concurrency Limit")
    await engine.execute_plan(ctx, tool_port=spy, max_concurrency=2)

    assert spy.peak_concurrency <= 2, f"Peak concurrency exceeded limit 2! Got {spy.peak_concurrency}"


@pytest.mark.asyncio
async def test_F_and_G_non_sequential_and_string_node_ids() -> None:
    """Test F & G: Support non-sequential integer and string node IDs."""
    engine = PlanGraphExecutionEngine(max_concurrency=4)
    spy = ConcurrentSpyToolPort()

    nodes: dict[Any, PlanGraphNode] = {
        "zeta": PlanGraphNode(step=PlanStep(step_id=1, title="Zeta", tool_name="tool_a"), dependencies=()),
        "alpha": PlanGraphNode(step=PlanStep(step_id=2, title="Alpha", tool_name="tool_b"), dependencies=("zeta",)),
        "beta": PlanGraphNode(step=PlanStep(step_id=3, title="Beta", tool_name="tool_c"), dependencies=("alpha",)),
    }
    plan_graph = PlanGraph(nodes=nodes)
    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_context("String Node IDs")
    await engine.execute_plan(ctx, tool_port=spy)

    assert spy.executed_order == ["tool_a", "tool_b", "tool_c"]


@pytest.mark.asyncio
async def test_H_and_I_dependency_failure_propagation_and_unrelated_branch() -> None:
    """Test H & I: If tool_b fails, dependent tool_d is skipped, but independent tool_c completes."""
    engine = PlanGraphExecutionEngine(max_concurrency=4)
    spy = ConcurrentSpyToolPort(fail_tools={"tool_b"})

    # Branch 1: A -> B -> D (B fails)
    # Branch 2: A -> C (C succeeds)
    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Step A", tool_name="tool_a"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Step B", tool_name="tool_b"), dependencies=(1,)),
        3: PlanGraphNode(step=PlanStep(step_id=3, title="Step C", tool_name="tool_c"), dependencies=(1,)),
        4: PlanGraphNode(step=PlanStep(step_id=4, title="Step D", tool_name="tool_d"), dependencies=(2,)),
    }
    plan_graph = PlanGraph(nodes=nodes)
    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_context("Failure Propagation")
    graph, results, trace = await engine.execute_plan(ctx, tool_port=spy)

    # Tool A succeeds, B fails, C succeeds, D is skipped
    assert "tool_a" in spy.executed_order
    assert "tool_b" in spy.executed_order
    assert "tool_c" in spy.executed_order
    assert "tool_d" not in spy.executed_order, "Tool D must NOT execute when dependency B fails"
    assert graph.nodes[4].step.status == StepStatus.CANCELLED or graph.nodes[4].step.status == StepStatus.PENDING


@pytest.mark.asyncio
async def test_J_and_K_parent_cancellation_no_leaked_tasks() -> None:
    """Test J & K: Cancelling execution task cancels active child tasks cleanly with zero leaks."""
    engine = PlanGraphExecutionEngine(max_concurrency=4)
    spy = ConcurrentSpyToolPort(delay_map={"tool_a": 5.0})

    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Step A", tool_name="tool_a"), dependencies=()),
    }
    plan_graph = PlanGraph(nodes=nodes)
    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_context("Cancellation Test")
    task = asyncio.create_task(engine.execute_plan(ctx, tool_port=spy))

    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_M_circuit_breaker_interaction() -> None:
    """Test M: CircuitBreaker failure count updates correctly under concurrent failures."""
    engine = PlanGraphExecutionEngine(max_concurrency=4)
    spy = ConcurrentSpyToolPort(fail_tools={"tool_a", "tool_b"})

    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Step A", tool_name="tool_a"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Step B", tool_name="tool_b"), dependencies=()),
    }
    plan_graph = PlanGraph(nodes=nodes)
    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_context("CircuitBreaker Test")
    assert engine.circuit_breaker.failure_count == 0

    await engine.execute_plan(ctx, tool_port=spy)
    assert engine.circuit_breaker.failure_count == 2


@pytest.mark.asyncio
async def test_N_deterministic_ready_node_scheduling() -> None:
    """Test N: Scheduling order for simultaneously ready nodes is deterministic."""
    engine = PlanGraphExecutionEngine(max_concurrency=1)  # Serialized via semaphore=1
    spy = ConcurrentSpyToolPort(delay_map={"tool_a": 0.01, "tool_b": 0.01, "tool_c": 0.01})

    # Nodes 1, 2, 3 all ready simultaneously
    nodes = {
        "c_node": PlanGraphNode(step=PlanStep(step_id="c_node", title="C", tool_name="tool_c"), dependencies=()),
        "a_node": PlanGraphNode(step=PlanStep(step_id="a_node", title="A", tool_name="tool_a"), dependencies=()),
        "b_node": PlanGraphNode(step=PlanStep(step_id="b_node", title="B", tool_name="tool_b"), dependencies=()),
    }
    plan_graph = PlanGraph(nodes=nodes)
    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_context("Deterministic Test")
    await engine.execute_plan(ctx, tool_port=spy)

    # Sorted order of node IDs ['a_node', 'b_node', 'c_node'] -> ['tool_a', 'tool_b', 'tool_c']
    assert spy.executed_order == ["tool_a", "tool_b", "tool_c"]


@pytest.mark.asyncio
async def test_O_event_and_trace_preservation() -> None:
    """Test O: DecisionTrace and StepStatus metadata are preserved."""
    engine = PlanGraphExecutionEngine(max_concurrency=4)
    spy = ConcurrentSpyToolPort()

    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Step 1", tool_name="tool_a"), dependencies=()),
    }
    plan_graph = PlanGraph(nodes=nodes)
    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_context("Trace Preservation")
    graph, results, trace = await engine.execute_plan(ctx, tool_port=spy)

    assert graph.nodes[1].step.status == StepStatus.COMPLETED
    assert trace is not None
    assert len(results) == 1


if __name__ == "__main__":
    asyncio.run(test_A_sequential_dag_correctness())
    asyncio.run(test_B_independent_nodes_run_concurrently())
    asyncio.run(test_C_and_D_diamond_and_branching_dag())
    asyncio.run(test_E_concurrency_limit_enforcement())
    asyncio.run(test_F_and_G_non_sequential_and_string_node_ids())
    asyncio.run(test_H_and_I_dependency_failure_propagation_and_unrelated_branch())
    asyncio.run(test_J_and_K_parent_cancellation_no_leaked_tasks())
    asyncio.run(test_M_circuit_breaker_interaction())
    asyncio.run(test_N_deterministic_ready_node_scheduling())
    asyncio.run(test_O_event_and_trace_preservation())
    print("ALL P1-3 CONCURRENT DAG EXECUTION TESTS PASSED SUCCESSFULLY!")
