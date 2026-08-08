"""Stress test verifying ExecutionScheduler parallel DAG execution with 1,000 nodes."""

from __future__ import annotations

import pytest

from nexusai.brain.domain.agent import PlanGraph, PlanGraphNode, PlanStep
from nexusai.brain.planner.scheduler import ExecutionScheduler
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult


class StressMockToolPort(IToolPort):
    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=request.tool_name,
            success=True,
            result_data="STRESS_OK",
        )


@pytest.mark.stress
@pytest.mark.asyncio
async def test_scheduler_1000_nodes_execution():
    """Execute a 1,000-node DAG graph through ExecutionScheduler with 16 parallel workers."""
    nodes: dict[int, PlanGraphNode] = {}
    edges: list[tuple[int, int]] = []

    # Root node
    nodes[1] = PlanGraphNode(
        step=PlanStep(step_id=1, title="Root Node", description="Root", tool_name="read_file"),
        dependencies=(),
    )

    # Create 999 parallel child nodes
    for i in range(2, 1001):
        nodes[i] = PlanGraphNode(
            step=PlanStep(
                step_id=i, title=f"Step {i}", description=f"Step {i}", tool_name="locate_file"
            ),
            dependencies=(1,),
        )
        edges.append((1, i))

    graph = PlanGraph(nodes=nodes, edges=tuple(edges))
    scheduler = ExecutionScheduler(max_workers=16)
    tool_port = StressMockToolPort()

    results = await scheduler.schedule_and_execute(graph, tool_port=tool_port)

    assert len(results) == 1000
    assert all(r.success for r in results)
