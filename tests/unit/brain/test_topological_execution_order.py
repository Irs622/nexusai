"""P0-3 Topological Execution Ordering Regression Test Suite.

Verifies:
- PlanGraphExecutionEngine resolves execution order using graphlib.TopologicalSorter driven by node dependencies.
- Node ID types (numeric, reverse lexical, non-sequential) do not affect topological execution order.
- Branching DAGs execute parents before children.
- Cycles are rejected prior to execution.
- Missing dependencies are rejected prior to execution.
- Spies record actual execution sequence.
- Provider spy verification strengthens P0-2 entrypoint checks.
"""

from __future__ import annotations

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
)
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.models.base import BaseModelProvider


class SpyToolPort(IToolPort):
    """Spy tool port recording the exact order of executed step node IDs."""

    def __init__(self) -> None:
        self.executed_order: list[Any] = []

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        node_id_str = request.execution_id.replace("step-", "")
        if node_id_str.isdigit():
            executed_id: Any = int(node_id_str)
        else:
            executed_id = node_id_str

        self.executed_order.append(executed_id)
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=request.tool_name,
            success=True,
            output=f"Executed {request.tool_name}",
        )


class SpyModelProvider(BaseModelProvider):
    """Spy model provider recording call counts and passed parameters."""

    def __init__(self, response: dict | None = None) -> None:
        self.response = response or {"type": "text", "content": "Spy response"}
        self.call_count = 0
        self.last_messages: list = []
        self.last_tools: list | None = None

    async def chat(self, messages: list, tools: list | None = None) -> dict:
        self.call_count += 1
        self.last_messages = messages
        self.last_tools = tools
        return dict(self.response)


def create_planning_context(description: str = "Test Goal") -> PlanningContext:
    goal = AgentGoal(description=description)
    return PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=("dummy_tool",)),
    )


# ------------------------------------------------------------------
# Test Cases A through G (Section 7)
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_topological_order_sequential_dag() -> None:
    """Test A: Sequential DAG (1 -> 2 -> 3)."""
    engine = PlanGraphExecutionEngine()
    spy = SpyToolPort()

    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Step 1", tool_name="dummy_tool"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Step 2", tool_name="dummy_tool"), dependencies=(1,)),
        3: PlanGraphNode(step=PlanStep(step_id=3, title="Step 3", tool_name="dummy_tool"), dependencies=(2,)),
    }
    edges = ((1, 2), (2, 3))
    plan_graph = PlanGraph(nodes=nodes, edges=edges)

    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_planning_context("Sequential DAG")
    await engine.execute_plan(ctx, tool_port=spy)

    assert spy.executed_order == [1, 2, 3], f"Expected [1, 2, 3], got {spy.executed_order}"


@pytest.mark.asyncio
async def test_topological_order_reverse_lexical_ids() -> None:
    """Test B: Reverse lexical IDs ('zeta' -> 'alpha' -> 'beta')."""
    engine = PlanGraphExecutionEngine()
    spy = SpyToolPort()

    nodes: dict[Any, PlanGraphNode] = {
        "zeta": PlanGraphNode(step=PlanStep(step_id=1, title="Zeta Root", tool_name="dummy_tool"), dependencies=()),
        "alpha": PlanGraphNode(step=PlanStep(step_id=2, title="Alpha Child", tool_name="dummy_tool"), dependencies=("zeta",)),
        "beta": PlanGraphNode(step=PlanStep(step_id=3, title="Beta Leaf", tool_name="dummy_tool"), dependencies=("alpha",)),
    }
    plan_graph = PlanGraph(nodes=nodes)

    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_planning_context("Reverse Lexical")
    await engine.execute_plan(ctx, tool_port=spy)

    assert spy.executed_order == ["zeta", "alpha", "beta"], f"Expected ['zeta', 'alpha', 'beta'], got {spy.executed_order}"


@pytest.mark.asyncio
async def test_topological_order_branching_dag() -> None:
    """Test C: Branching DAG (A -> B/C -> D)."""
    engine = PlanGraphExecutionEngine()
    spy = SpyToolPort()

    nodes: dict[Any, PlanGraphNode] = {
        "A": PlanGraphNode(step=PlanStep(step_id=1, title="A Root", tool_name="dummy_tool"), dependencies=()),
        "B": PlanGraphNode(step=PlanStep(step_id=2, title="B Branch", tool_name="dummy_tool"), dependencies=("A",)),
        "C": PlanGraphNode(step=PlanStep(step_id=3, title="C Branch", tool_name="dummy_tool"), dependencies=("A",)),
        "D": PlanGraphNode(step=PlanStep(step_id=4, title="D Join", tool_name="dummy_tool"), dependencies=("B", "C")),
    }
    plan_graph = PlanGraph(nodes=nodes)

    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_planning_context("Branching DAG")
    await engine.execute_plan(ctx, tool_port=spy)

    order = spy.executed_order
    assert order[0] == "A", "Root A must execute first"
    assert order.index("B") < order.index("D"), "B must execute before D"
    assert order.index("C") < order.index("D"), "C must execute before D"
    assert order[-1] == "D", "Join node D must execute last"


@pytest.mark.asyncio
async def test_topological_order_non_sequential_node_ids() -> None:
    """Test D: Non-sequential node IDs (100 -> 2 -> 57)."""
    engine = PlanGraphExecutionEngine()
    spy = SpyToolPort()

    nodes = {
        100: PlanGraphNode(step=PlanStep(step_id=100, title="Node 100", tool_name="dummy_tool"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Node 2", tool_name="dummy_tool"), dependencies=(100,)),
        57: PlanGraphNode(step=PlanStep(step_id=57, title="Node 57", tool_name="dummy_tool"), dependencies=(2,)),
    }
    plan_graph = PlanGraph(nodes=nodes)

    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_planning_context("Non-sequential Node IDs")
    await engine.execute_plan(ctx, tool_port=spy)

    assert spy.executed_order == [100, 2, 57], f"Expected [100, 2, 57], got {spy.executed_order}"


@pytest.mark.asyncio
async def test_topological_order_cycle_detection() -> None:
    """Test E: Cycle detection (A -> B -> C -> A) fails before execution."""
    engine = PlanGraphExecutionEngine()
    spy = SpyToolPort()

    nodes: dict[Any, PlanGraphNode] = {
        "A": PlanGraphNode(step=PlanStep(step_id=1, title="A", tool_name="dummy_tool"), dependencies=("C",)),
        "B": PlanGraphNode(step=PlanStep(step_id=2, title="B", tool_name="dummy_tool"), dependencies=("A",)),
        "C": PlanGraphNode(step=PlanStep(step_id=3, title="C", tool_name="dummy_tool"), dependencies=("B",)),
    }
    plan_graph = PlanGraph(nodes=nodes)

    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_planning_context("Cycle Test")
    with pytest.raises(RuntimeError, match="PlanGraph validation failed|PlanGraph contains a dependency cycle"):
        await engine.execute_plan(ctx, tool_port=spy)

    assert len(spy.executed_order) == 0, "No nodes should execute if graph is cyclic"


@pytest.mark.asyncio
async def test_topological_order_missing_dependency() -> None:
    """Test F: Missing dependency (A depends on UNKNOWN) fails before execution."""
    engine = PlanGraphExecutionEngine()
    spy = SpyToolPort()

    nodes: dict[Any, PlanGraphNode] = {
        "A": PlanGraphNode(step=PlanStep(step_id=1, title="A", tool_name="dummy_tool"), dependencies=("UNKNOWN",)),
    }
    plan_graph = PlanGraph(nodes=nodes)

    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    ctx = create_planning_context("Missing Dependency Test")
    with pytest.raises(RuntimeError, match="non-existent dependency step|missing from PlanGraph"):
        await engine.execute_plan(ctx, tool_port=spy)

    assert len(spy.executed_order) == 0, "No nodes should execute if dependency is missing"


@pytest.mark.asyncio
async def test_provider_spy_synthesis_call_verification() -> None:
    """Test G: Provider spy verification asserting model_provider.chat() is called exactly once for synthesis."""
    spy_provider = SpyModelProvider({"type": "text", "content": "Synthesized output"})
    coordinator = BrainCoordinator(model_provider=spy_provider)

    assert spy_provider.call_count == 0

    res = await coordinator.process_user_input("Synthesize user prompt")

    assert spy_provider.call_count == 1
    assert res["content"] == "Synthesized output"
    assert "trace_id" in res
