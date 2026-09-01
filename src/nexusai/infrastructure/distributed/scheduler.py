"""DistributedExecutionScheduler coordinating PlanGraph DAG branch execution across worker clusters."""

from __future__ import annotations

import asyncio

from nexusai.brain.domain.agent import PlanGraph, StepStatus
from nexusai.brain.domain.execution_coordination import WorkerIdentity
from nexusai.brain.ports.execution_coordinator_port import IExecutionCoordinator
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.execution_policy import CircuitBreaker, ExecutionPolicy
from nexusai.infrastructure.distributed.pool import DistributedWorkerPool, RoutingStrategy
from nexusai.infrastructure.distributed.worker_node import WorkerNode


class DistributedExecutionScheduler:
    """Multi-node DAG scheduler executing independent PlanGraph branches across a cluster of WorkerNodes."""

    def __init__(
        self,
        pool: DistributedWorkerPool,
        coordinator: IExecutionCoordinator | None = None,
        policy: ExecutionPolicy | None = None,
        max_concurrent_tasks: int = 8,
        session_id: str = "cluster-session",
    ) -> None:
        self.pool = pool
        self.coordinator = coordinator
        self.policy = policy or ExecutionPolicy()
        self.max_concurrent_tasks = max_concurrent_tasks
        self.session_id = session_id
        self.circuit_breaker = CircuitBreaker()

    async def schedule_and_execute(
        self,
        graph: PlanGraph,
        tool_port: IToolPort,
        routing_strategy: RoutingStrategy | None = None,
    ) -> list[ToolExecutionResult]:
        """Schedule and execute PlanGraph DAG nodes concurrently across cluster worker nodes."""

        if not graph.nodes:
            return []

        # Build in-degree dependency counter and reverse adjacency map
        in_degree: dict[int | str, int] = {
            node_id: len(node.dependencies) for node_id, node in graph.nodes.items()
        }
        adj: dict[int | str, list[int | str]] = {node_id: [] for node_id in graph.nodes}
        for parent, child in graph.edges:
            if parent in adj:
                adj[parent].append(child)

        ready_queue: asyncio.Queue[int | str] = asyncio.Queue()
        results_map: dict[int | str, ToolExecutionResult] = {}
        lock = asyncio.Lock()
        completed_nodes_count = 0
        total_nodes = len(graph.nodes)

        # Seed initial ready queue (in-degree == 0)
        for node_id, count in in_degree.items():
            if count == 0:
                await ready_queue.put(node_id)

        async def worker_loop() -> None:
            nonlocal completed_nodes_count
            while True:
                async with lock:
                    if completed_nodes_count >= total_nodes:
                        break

                try:
                    node_id = await asyncio.wait_for(ready_queue.get(), timeout=0.1)
                except (asyncio.TimeoutError, asyncio.QueueEmpty):
                    async with lock:
                        if completed_nodes_count >= total_nodes:
                            break
                    await asyncio.sleep(0.02)
                    continue

                node = graph.nodes[node_id]
                step = node.step
                step.status = StepStatus.RUNNING

                res: ToolExecutionResult

                # Non-tool step completes immediately
                if not step.tool_name:
                    step.status = StepStatus.COMPLETED
                    res = ToolExecutionResult(
                        request_id=f"sched-{step.step_id}",
                        tool_name="noop",
                        success=True,
                        result_data="NOOP_COMPLETED",
                    )
                else:
                    req = ToolExecutionRequest(
                        tool_name=step.tool_name,
                        arguments=step.arguments,
                        execution_id=f"sched-{step.step_id}",
                    )

                    # Select a worker node from the cluster pool
                    selected_node: WorkerNode | None = None
                    for _ in range(20):  # Retry up to 1 second if all nodes temporarily busy
                        selected_node = await self.pool.select_node(strategy=routing_strategy)
                        if selected_node:
                            break
                        await asyncio.sleep(0.05)

                    if not selected_node:
                        step.status = StepStatus.FAILED
                        res = ToolExecutionResult(
                            request_id=req.execution_id or f"sched-{step.step_id}",
                            tool_name=step.tool_name,
                            success=False,
                            error_message="NO_WORKER_AVAILABLE: All cluster worker nodes are busy or offline",
                        )
                    else:
                        # Distributed Lease Management with IExecutionCoordinator
                        lease = None
                        worker_ident = WorkerIdentity(
                            worker_id=selected_node.node_id,
                            host_id=selected_node.endpoint,
                        )

                        if self.coordinator:
                            try:
                                lease = await self.coordinator.acquire_execution_lease(
                                    execution_id=str(req.execution_id or f"sched-{step.step_id}"),
                                    session_id=self.session_id,
                                    worker=worker_ident,
                                    ttl_seconds=15.0,
                                )
                            except Exception as lease_err:
                                step.status = StepStatus.FAILED
                                res = ToolExecutionResult(
                                    request_id=req.execution_id or f"sched-{step.step_id}",
                                    tool_name=step.tool_name,
                                    success=False,
                                    error_message=f"LEASE_ACQUISITION_FAILED: {lease_err}",
                                )
                                async with lock:
                                    results_map[node_id] = res
                                    completed_nodes_count += 1
                                ready_queue.task_done()
                                continue

                        # Execute request on the selected worker node
                        try:
                            res = await selected_node.execute(req, tool_port)
                            step.status = StepStatus.COMPLETED if res.success else StepStatus.FAILED
                        except Exception as exec_err:
                            # Automated failover: attempt lease recovery and failover to another worker node
                            failover_node = None
                            if self.coordinator and lease:
                                try:
                                    # Pick an alternate worker
                                    candidates = [
                                        n
                                        for n in self.pool.get_healthy_nodes()
                                        if n.node_id != selected_node.node_id
                                        and n.can_accept_task()
                                    ]
                                    if candidates:
                                        failover_node = candidates[0]
                                        new_ident = WorkerIdentity(
                                            worker_id=failover_node.node_id,
                                            host_id=failover_node.endpoint,
                                        )
                                        lease = (
                                            await self.coordinator.recover_expired_execution_lease(
                                                execution_id=str(
                                                    req.execution_id or f"sched-{step.step_id}"
                                                ),
                                                new_worker=new_ident,
                                                ttl_seconds=15.0,
                                            )
                                        )
                                        res = await failover_node.execute(req, tool_port)
                                        step.status = (
                                            StepStatus.COMPLETED
                                            if res.success
                                            else StepStatus.FAILED
                                        )
                                    else:
                                        step.status = StepStatus.FAILED
                                        res = ToolExecutionResult(
                                            request_id=req.execution_id or f"sched-{step.step_id}",
                                            tool_name=step.tool_name,
                                            success=False,
                                            error_message=f"FAILOVER_FAILED: No healthy candidate worker available (original: {exec_err})",
                                        )
                                except Exception as fo_err:
                                    step.status = StepStatus.FAILED
                                    res = ToolExecutionResult(
                                        request_id=req.execution_id or f"sched-{step.step_id}",
                                        tool_name=step.tool_name,
                                        success=False,
                                        error_message=f"FAILOVER_FAILED: {fo_err} (original: {exec_err})",
                                    )
                            else:
                                step.status = StepStatus.FAILED
                                res = ToolExecutionResult(
                                    request_id=req.execution_id or f"sched-{step.step_id}",
                                    tool_name=step.tool_name,
                                    success=False,
                                    error_message=str(exec_err),
                                )
                        finally:
                            # Release execution lease cleanly
                            if self.coordinator and lease:
                                try:
                                    await self.coordinator.release_execution_lease(
                                        lease_id=lease.lease_id,
                                        worker=worker_ident,
                                    )
                                except Exception:
                                    pass

                async with lock:
                    results_map[node_id] = res
                    completed_nodes_count += 1

                    # Unlock dependent child nodes upon success
                    if res.success:
                        for child_id in adj.get(node_id, []):
                            in_degree[child_id] -= 1
                            if in_degree[child_id] == 0:
                                await ready_queue.put(child_id)

                ready_queue.task_done()

        # Run worker loop pool
        workers = [asyncio.create_task(worker_loop()) for _ in range(self.max_concurrent_tasks)]
        await asyncio.gather(*workers, return_exceptions=True)

        return [results_map[nid] for nid in sorted(results_map.keys(), key=str)]
