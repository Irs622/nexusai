"""ExecutionScheduler for executing independent PlanGraph DAG branches concurrently."""

from __future__ import annotations

import asyncio

from nexusai.brain.domain.agent import PlanGraph, StepStatus
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.execution_policy import CircuitBreaker, ExecutionPolicy


class ExecutionScheduler:
    """Multi-worker async DAG scheduler executing independent PlanGraph branches concurrently."""

    def __init__(self, policy: ExecutionPolicy | None = None, max_workers: int = 4) -> None:
        self.policy = policy or ExecutionPolicy()
        self.max_workers = max_workers
        self.circuit_breaker = CircuitBreaker()

    async def schedule_and_execute(
        self,
        graph: PlanGraph,
        tool_port: IToolPort,
    ) -> list[ToolExecutionResult]:
        """Schedule and execute PlanGraph DAG nodes concurrently using async worker pool."""

        if not graph.nodes:
            return []

        # Build in-degree dependency counter and reverse adjacency map
        in_degree: dict[int, int] = {
            node_id: len(node.dependencies) for node_id, node in graph.nodes.items()
        }
        adj: dict[int, list[int]] = {node_id: [] for node_id in graph.nodes}
        for parent, child in graph.edges:
            if parent in adj:
                adj[parent].append(child)

        ready_queue: asyncio.Queue[int] = asyncio.Queue()
        results_map: dict[int, ToolExecutionResult] = {}
        lock = asyncio.Lock()

        # Seed initial ready queue (in-degree == 0)
        for node_id, count in in_degree.items():
            if count == 0:
                await ready_queue.put(node_id)

        async def worker() -> None:
            while True:
                try:
                    node_id = ready_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                node = graph.nodes[node_id]
                step = node.step
                step.status = StepStatus.RUNNING

                if step.tool_name:
                    req = ToolExecutionRequest(
                        tool_name=step.tool_name,
                        arguments=step.arguments,
                        execution_id=f"sched-{step.step_id}",
                    )
                    try:
                        res = await tool_port.execute(req)
                        step.status = StepStatus.COMPLETED if res.success else StepStatus.FAILED
                    except Exception as err:
                        step.status = StepStatus.FAILED
                        res = ToolExecutionResult(
                            request_id=f"sched-{step.step_id}",
                            tool_name=step.tool_name,
                            success=False,
                            error_message=str(err),
                        )
                else:
                    step.status = StepStatus.COMPLETED
                    res = ToolExecutionResult(
                        request_id=f"sched-{step.step_id}",
                        tool_name="noop",
                        success=True,
                        result_data="NOOP_COMPLETED",
                    )

                async with lock:
                    results_map[node_id] = res

                    # Unlock dependent child nodes
                    for child_id in adj.get(node_id, []):
                        in_degree[child_id] -= 1
                        if in_degree[child_id] == 0:
                            await ready_queue.put(child_id)

                ready_queue.task_done()

        # Run worker pool until queue is drained
        workers = [asyncio.create_task(worker()) for _ in range(self.max_workers)]
        await asyncio.gather(*workers, return_exceptions=True)

        return [results_map[nid] for nid in sorted(results_map.keys())]
