"""ExecutionScheduler for executing independent PlanGraph DAG branches concurrently."""

from __future__ import annotations

import asyncio
from typing import Any

from nexusai.brain.domain.agent import PlanGraph, StepStatus
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.execution_policy import CircuitBreaker, ExecutionPolicy


class ExecutionScheduler:
    """Multi-worker async DAG scheduler executing independent PlanGraph branches concurrently.

    Dependencies are the union of each node's ``dependencies`` and the graph's ``edges``.
    A node runs only after every dependency completed successfully; dependents of a failed
    node are SKIPPED. Nodes that can never run (unknown dependency or a cycle) are reported
    as failed results instead of being dropped, so the result list always covers every node.
    """

    def __init__(self, policy: ExecutionPolicy | None = None, max_workers: int = 4) -> None:
        self.policy = policy or ExecutionPolicy()
        self.max_workers = max(1, max_workers)
        self.circuit_breaker = CircuitBreaker()

    async def schedule_and_execute(
        self,
        graph: PlanGraph,
        tool_port: IToolPort,
    ) -> list[ToolExecutionResult]:
        """Schedule and execute PlanGraph DAG nodes concurrently, bounded by ``max_workers``."""

        if not graph.nodes:
            return []

        parents: dict[Any, set[Any]] = {
            node_id: set(node.dependencies) for node_id, node in graph.nodes.items()
        }
        for parent, child in graph.edges:
            if child in parents:
                parents[child].add(parent)

        children: dict[Any, list[Any]] = {node_id: [] for node_id in graph.nodes}
        results_map: dict[Any, ToolExecutionResult] = {}

        for node_id, deps in parents.items():
            unknown = [d for d in deps if d not in graph.nodes]
            if unknown:
                results_map[node_id] = self._skip(graph, node_id, f"unknown dependencies {unknown}")
            for dep in deps:
                if dep in children:
                    children[dep].append(node_id)

        remaining: dict[Any, int] = {
            node_id: len(deps) for node_id, deps in parents.items() if node_id not in results_map
        }
        semaphore = asyncio.Semaphore(self.max_workers)
        running: dict[asyncio.Task[ToolExecutionResult], Any] = {}

        def resolve(finished_id: Any) -> None:
            """Release (or transitively skip) the dependents of a finished node."""
            stack = [finished_id]
            while stack:
                node_id = stack.pop()
                for child_id in children[node_id]:
                    if child_id in results_map or child_id not in remaining:
                        continue
                    if not results_map[node_id].success:
                        results_map[child_id] = self._skip(
                            graph, child_id, f"dependency '{node_id}' did not succeed"
                        )
                        stack.append(child_id)
                        continue
                    remaining[child_id] -= 1
                    if remaining[child_id] == 0:
                        start(child_id)

        def start(node_id: Any) -> None:
            task = asyncio.create_task(self._run_node(graph, node_id, tool_port, semaphore))
            running[task] = node_id

        # Nodes whose dependencies already failed before scheduling (unknown deps).
        for node_id in list(results_map):
            resolve(node_id)

        for node_id, count in list(remaining.items()):
            if count == 0 and node_id not in results_map:
                start(node_id)

        while running:
            done, _ = await asyncio.wait(running.keys(), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                node_id = running.pop(task)
                results_map[node_id] = task.result()
                resolve(node_id)

        # Anything left was blocked by a dependency cycle.
        for node_id in graph.nodes:
            if node_id not in results_map:
                results_map[node_id] = self._skip(graph, node_id, "dependency cycle detected")

        try:
            ordered = sorted(results_map.keys())
        except TypeError:
            ordered = sorted(results_map.keys(), key=str)
        return [results_map[nid] for nid in ordered]

    @staticmethod
    async def _run_node(
        graph: PlanGraph,
        node_id: Any,
        tool_port: IToolPort,
        semaphore: asyncio.Semaphore,
    ) -> ToolExecutionResult:
        step = graph.nodes[node_id].step
        async with semaphore:
            step.status = StepStatus.RUNNING
            if not step.tool_name:
                step.status = StepStatus.COMPLETED
                return ToolExecutionResult(
                    request_id=f"sched-{step.step_id}",
                    tool_name="noop",
                    success=True,
                    result_data="NOOP_COMPLETED",
                )

            req = ToolExecutionRequest(
                tool_name=step.tool_name,
                arguments=step.arguments,
                execution_id=f"sched-{step.step_id}",
            )
            try:
                res = await tool_port.execute(req)
            except Exception as err:
                res = ToolExecutionResult(
                    request_id=f"sched-{step.step_id}",
                    tool_name=step.tool_name,
                    success=False,
                    error_message=str(err),
                )
            step.status = StepStatus.COMPLETED if res.success else StepStatus.FAILED
            return res

    @staticmethod
    def _skip(graph: PlanGraph, node_id: Any, reason: str) -> ToolExecutionResult:
        step = graph.nodes[node_id].step
        step.status = StepStatus.SKIPPED
        return ToolExecutionResult(
            request_id=f"sched-{step.step_id}",
            tool_name=step.tool_name or "noop",
            success=False,
            error_message=f"Skipped: {reason}",
        )
