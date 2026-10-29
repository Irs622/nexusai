"""Unit tests for ExecutionScheduler dependency semantics: failure propagation, concurrency, cycles."""

from __future__ import annotations

import asyncio

import pytest

from nexusai.brain.domain.agent import PlanGraph, PlanGraphNode, PlanStep, StepStatus
from nexusai.brain.planner.scheduler import ExecutionScheduler
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult


class RecordingToolPort(IToolPort):
    """Tool port that fails selected tools and tracks peak concurrency."""

    def __init__(self, failing: set[str] | None = None, delay: float = 0.0) -> None:
        self.failing = failing or set()
        self.delay = delay
        self.executed: list[str] = []
        self.active = 0
        self.peak = 0

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            self.executed.append(request.tool_name)
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=request.tool_name not in self.failing,
            )
        finally:
            self.active -= 1


def _node(step_id: int, deps: tuple[int, ...] = ()) -> PlanGraphNode:
    return PlanGraphNode(
        step=PlanStep(
            step_id=step_id, title=f"S{step_id}", description="", tool_name=f"tool_{step_id}"
        ),
        dependencies=deps,
    )


@pytest.mark.asyncio
async def test_failed_dependency_skips_dependents_transitively() -> None:
    graph = PlanGraph(nodes={1: _node(1), 2: _node(2, (1,)), 3: _node(3, (2,)), 4: _node(4)})
    port = RecordingToolPort(failing={"tool_1"})

    results = await ExecutionScheduler().schedule_and_execute(graph, port)

    assert sorted(port.executed) == ["tool_1", "tool_4"]
    assert [r.success for r in results] == [False, False, False, True]
    assert "dependency '1'" in (results[1].error_message or "")
    assert graph.nodes[3].step.status == StepStatus.SKIPPED


@pytest.mark.asyncio
async def test_branches_after_root_run_concurrently() -> None:
    nodes = {1: _node(1)} | {i: _node(i, (1,)) for i in range(2, 6)}
    port = RecordingToolPort(delay=0.02)

    results = await ExecutionScheduler(max_workers=4).schedule_and_execute(
        PlanGraph(nodes=nodes), port
    )

    assert all(r.success for r in results)
    assert port.peak == 4


@pytest.mark.asyncio
async def test_edges_only_dependencies_are_respected() -> None:
    graph = PlanGraph(nodes={1: _node(1), 2: _node(2)}, edges=((1, 2),))
    port = RecordingToolPort(failing={"tool_1"})

    results = await ExecutionScheduler().schedule_and_execute(graph, port)

    assert port.executed == ["tool_1"]
    assert results[1].success is False


@pytest.mark.asyncio
async def test_cycles_and_unknown_dependencies_are_reported_not_dropped() -> None:
    graph = PlanGraph(nodes={1: _node(1, (2,)), 2: _node(2, (1,)), 3: _node(3, (99,)), 4: _node(4)})
    port = RecordingToolPort()

    results = await ExecutionScheduler().schedule_and_execute(graph, port)

    assert len(results) == 4
    assert port.executed == ["tool_4"]
    assert "cycle" in (results[0].error_message or "")
    assert "unknown dependencies" in (results[2].error_message or "")


@pytest.mark.asyncio
async def test_long_failed_chain_does_not_recurse() -> None:
    nodes = {1: _node(1)} | {i: _node(i, (i - 1,)) for i in range(2, 3001)}
    port = RecordingToolPort(failing={"tool_1"})

    results = await ExecutionScheduler().schedule_and_execute(PlanGraph(nodes=nodes), port)

    assert len(results) == 3000
    assert not any(r.success for r in results)
