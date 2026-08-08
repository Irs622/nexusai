"""Benchmark script measuring parallel DAG ExecutionScheduler worker dispatch throughput."""

from __future__ import annotations

import asyncio
import time
from nexusai.brain.domain.agent import PlanGraph, PlanGraphNode, PlanStep
from nexusai.brain.planner.scheduler import ExecutionScheduler
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult


class FastToolPort(IToolPort):
    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        return ToolExecutionResult(request_id=request.execution_id, tool_name=request.tool_name, success=True, result_data="OK")


async def run_scheduler_benchmark(node_count: int = 200, max_workers: int = 8) -> dict[str, float]:
    """Benchmark ExecutionScheduler executing a parallel DAG with node_count steps."""
    nodes: dict[int, PlanGraphNode] = {}
    edges: list[tuple[int, int]] = []

    # Root node
    nodes[1] = PlanGraphNode(step=PlanStep(step_id=1, title="Root Node", description="Root", tool_name="read_file"), dependencies=())

    # Create parallel child nodes depending on root
    for i in range(2, node_count + 1):
        nodes[i] = PlanGraphNode(step=PlanStep(step_id=i, title=f"Step {i}", description=f"Step {i}", tool_name="locate_file"), dependencies=(1,))
        edges.append((1, i))

    graph = PlanGraph(nodes=nodes, edges=tuple(edges))
    scheduler = ExecutionScheduler(max_workers=max_workers)
    tool_port = FastToolPort()

    t0 = time.perf_counter()
    results = await scheduler.schedule_and_execute(graph, tool_port=tool_port)
    duration_sec = time.perf_counter() - t0
    throughput_nodes_sec = len(results) / duration_sec

    print(f"=== ExecutionScheduler Benchmark ({node_count} nodes, {max_workers} workers) ===")
    print(f"  Duration      : {duration_sec:.4f} s")
    print(f"  Executed Steps: {len(results)}")
    print(f"  Throughput    : {throughput_nodes_sec:.2f} nodes/sec")

    return {
        "duration_sec": duration_sec,
        "throughput_nodes_sec": throughput_nodes_sec,
    }


if __name__ == "__main__":
    asyncio.run(run_scheduler_benchmark())
