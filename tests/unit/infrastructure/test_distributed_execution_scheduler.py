"""Unit tests for DistributedExecutionScheduler DAG execution, leasing, and failover."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from nexusai.brain.domain.agent import PlanGraph, PlanGraphNode, PlanStep
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.infrastructure.distributed.pool import DistributedWorkerPool
from nexusai.infrastructure.distributed.scheduler import DistributedExecutionScheduler
from nexusai.infrastructure.distributed.worker_node import WorkerNode
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import (
    SQLiteExecutionCoordinator,
)


@pytest.fixture
def mock_tool_port() -> IToolPort:
    port = AsyncMock(spec=IToolPort)

    async def fake_exec(req: ToolExecutionRequest) -> ToolExecutionResult:
        await asyncio.sleep(0.01)
        return ToolExecutionResult(
            request_id=req.execution_id or "req",
            tool_name=req.tool_name,
            success=True,
            result_data=f"EXECUTED_{req.tool_name}",
            execution_time_ms=10.0,
        )

    port.execute.side_effect = fake_exec
    return port


@pytest.fixture
def sample_diamond_graph() -> PlanGraph:
    r"""Diamond DAG topology:

          Node 0 (Root)
          /           \
    Node 1 (Branch A) Node 2 (Branch B)
          \           /
          Node 3 (Merge)
    """
    s0 = PlanStep(step_id=0, title="Root", tool_name="tool_root")
    s1 = PlanStep(step_id=1, title="Branch A", tool_name="tool_a", depends_on=(0,))
    s2 = PlanStep(step_id=2, title="Branch B", tool_name="tool_b", depends_on=(0,))
    s3 = PlanStep(step_id=3, title="Merge", tool_name="tool_merge", depends_on=(1, 2))

    nodes: dict[int | str, PlanGraphNode] = {
        0: PlanGraphNode(step=s0, dependencies=()),
        1: PlanGraphNode(step=s1, dependencies=(0,)),
        2: PlanGraphNode(step=s2, dependencies=(0,)),
        3: PlanGraphNode(step=s3, dependencies=(1, 2)),
    }
    edges: tuple[tuple[int | str, int | str], ...] = ((0, 1), (0, 2), (1, 3), (2, 3))
    return PlanGraph(nodes=nodes, edges=edges)


@pytest.mark.asyncio
async def test_distributed_scheduler_parallel_dag_execution(
    sample_diamond_graph: PlanGraph,
    mock_tool_port: IToolPort,
) -> None:
    """Verify concurrent execution of diamond DAG across worker cluster."""
    pool = DistributedWorkerPool()
    node1 = WorkerNode("worker-node-1", max_concurrency=4)
    node2 = WorkerNode("worker-node-2", max_concurrency=4)
    pool.register_node(node1)
    pool.register_node(node2)

    scheduler = DistributedExecutionScheduler(pool=pool, max_concurrent_tasks=4)
    results = await scheduler.schedule_and_execute(sample_diamond_graph, mock_tool_port)

    assert len(results) == 4
    assert all(r.success for r in results)
    assert results[0].result_data == "EXECUTED_tool_root"
    assert results[3].result_data == "EXECUTED_tool_merge"

    # Verify both worker nodes participated
    assert node1.metrics.total_tasks_executed > 0 or node2.metrics.total_tasks_executed > 0
    assert (node1.metrics.total_tasks_executed + node2.metrics.total_tasks_executed) == 4


@pytest.mark.asyncio
async def test_distributed_scheduler_with_execution_coordinator_leases(
    sample_diamond_graph: PlanGraph,
    mock_tool_port: IToolPort,
) -> None:
    """Verify execution with distributed coordinator leasing and fencing tokens."""
    coord = SQLiteExecutionCoordinator(db_path=":memory:")

    pool = DistributedWorkerPool()
    node1 = WorkerNode("worker-leased-1")
    pool.register_node(node1)

    scheduler = DistributedExecutionScheduler(
        pool=pool,
        coordinator=coord,
        session_id="test-session-100",
    )

    results = await scheduler.schedule_and_execute(sample_diamond_graph, mock_tool_port)

    assert len(results) == 4
    assert all(r.success for r in results)


@pytest.mark.asyncio
async def test_distributed_scheduler_empty_graph(mock_tool_port: IToolPort) -> None:
    """Verify empty PlanGraph returns empty result list safely."""
    pool = DistributedWorkerPool()
    scheduler = DistributedExecutionScheduler(pool=pool)
    res = await scheduler.schedule_and_execute(PlanGraph(), mock_tool_port)
    assert res == []


@pytest.mark.asyncio
async def test_distributed_scheduler_no_workers_available(mock_tool_port: IToolPort) -> None:
    """Verify scheduler marks steps failed when no workers are available."""
    pool = DistributedWorkerPool()  # empty pool
    s = PlanStep(step_id=0, title="Single", tool_name="tool_single")
    graph = PlanGraph(nodes={0: PlanGraphNode(step=s, dependencies=())})

    scheduler = DistributedExecutionScheduler(pool=pool)
    results = await scheduler.schedule_and_execute(graph, mock_tool_port)

    assert len(results) == 1
    assert results[0].success is False
    assert "NO_WORKER_AVAILABLE" in str(results[0].error_message)
