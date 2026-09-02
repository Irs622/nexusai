"""Unit tests for WorkerHeartbeatSupervisor, WorkerAutoScaler, and ClusterOrchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from nexusai.infrastructure.distributed.autoscaler import (
    ScalingDirection,
    WorkerAutoScaler,
)
from nexusai.infrastructure.distributed.cluster_manager import ClusterOrchestrator
from nexusai.infrastructure.distributed.pool import DistributedWorkerPool
from nexusai.infrastructure.distributed.supervisor import WorkerHeartbeatSupervisor
from nexusai.infrastructure.distributed.worker_node import WorkerNode, WorkerNodeStatus


@pytest.mark.unit
@pytest.mark.asyncio
async def test_heartbeat_supervisor_success_and_metrics() -> None:
    """Verify heartbeat ping execution and latency tracking on healthy nodes."""
    pool = DistributedWorkerPool()
    node1 = WorkerNode(node_id="worker-01", max_concurrency=4)
    node2 = WorkerNode(node_id="worker-02", max_concurrency=4)
    pool.register_node(node1)
    pool.register_node(node2)

    supervisor = WorkerHeartbeatSupervisor(pool=pool, check_interval_seconds=0.1)

    results = await supervisor.check_all_nodes()
    assert results["worker-01"] is True
    assert results["worker-02"] is True

    tracker1 = supervisor.get_tracker("worker-01")
    assert tracker1.consecutive_successes == 1
    assert tracker1.consecutive_failures == 0
    assert tracker1.last_ping_latency_ms >= 0.0
    assert not tracker1.is_evicted


@pytest.mark.unit
@pytest.mark.asyncio
async def test_heartbeat_supervisor_dead_node_eviction() -> None:
    """Verify dead worker eviction when consecutive ping failures reach threshold."""
    pool = DistributedWorkerPool()
    node = WorkerNode(node_id="failing-worker", max_concurrency=4)
    pool.register_node(node)

    evicted_nodes: list[WorkerNode] = []

    def on_evicted(n: WorkerNode) -> None:
        evicted_nodes.append(n)

    supervisor = WorkerHeartbeatSupervisor(
        pool=pool,
        max_consecutive_failures=3,
        on_node_evicted=on_evicted,
    )

    # Mock failing ping
    node.ping = AsyncMock(return_value=False)

    # 1st failure
    res1 = await supervisor.check_node(node)
    assert not res1
    assert node.status == WorkerNodeStatus.ONLINE
    assert len(evicted_nodes) == 0

    # 2nd failure
    res2 = await supervisor.check_node(node)
    assert not res2
    assert node.status == WorkerNodeStatus.ONLINE
    assert len(evicted_nodes) == 0

    # 3rd failure -> Eviction triggered
    res3 = await supervisor.check_node(node)
    assert not res3
    assert node.status == WorkerNodeStatus.OFFLINE
    assert len(evicted_nodes) == 1
    assert evicted_nodes[0].node_id == "failing-worker"

    tracker = supervisor.get_tracker("failing-worker")
    assert tracker.is_evicted is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_heartbeat_supervisor_auto_recovery() -> None:
    """Verify automatic recovery of an evicted/offline node after consecutive successful pings."""
    pool = DistributedWorkerPool()
    node = WorkerNode(node_id="recovered-worker", max_concurrency=4)
    node.status = WorkerNodeStatus.OFFLINE
    pool.register_node(node)

    recovered_nodes: list[WorkerNode] = []

    def on_recovered(n: WorkerNode) -> None:
        recovered_nodes.append(n)

    supervisor = WorkerHeartbeatSupervisor(
        pool=pool,
        recovery_threshold=2,
        on_node_recovered=on_recovered,
    )
    tracker = supervisor.get_tracker("recovered-worker")
    tracker.is_evicted = True

    # Mock successful ping
    node.ping = AsyncMock(return_value=True)

    # 1st successful ping (threshold not met yet)
    await supervisor.check_node(node)
    assert node.status == WorkerNodeStatus.OFFLINE
    assert len(recovered_nodes) == 0

    # 2nd successful ping -> Auto-recovery triggered
    await supervisor.check_node(node)
    assert node.status == WorkerNodeStatus.ONLINE
    assert not tracker.is_evicted
    assert len(recovered_nodes) == 1
    assert recovered_nodes[0].node_id == "recovered-worker"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_autoscaler_scale_out_and_bounds() -> None:
    """Verify auto-scaler scales out upon queue pressure up to max_nodes ceiling."""
    pool = DistributedWorkerPool()
    base_node = WorkerNode(node_id="worker-static-1", max_concurrency=4)
    pool.register_node(base_node)

    autoscaler = WorkerAutoScaler(
        pool=pool,
        min_nodes=1,
        max_nodes=3,
        cooldown_seconds=0.0,
    )

    # 1. Scale out due to backlog tasks
    event1 = await autoscaler.evaluate_and_scale(backlog_tasks=4)
    assert event1 is not None
    assert event1.direction == ScalingDirection.SCALE_OUT
    assert pool.total_nodes == 2
    assert "worker-auto-001" in pool._nodes

    # 2. Scale out again
    event2 = await autoscaler.evaluate_and_scale(backlog_tasks=4)
    assert event2 is not None
    assert event2.direction == ScalingDirection.SCALE_OUT
    assert pool.total_nodes == 3

    # 3. Scale out capped at max_nodes
    event3 = await autoscaler.evaluate_and_scale(backlog_tasks=4)
    assert event3 is None
    assert pool.total_nodes == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_autoscaler_scale_in_and_floor() -> None:
    """Verify auto-scaler scales in idle dynamic nodes down to min_nodes floor."""
    pool = DistributedWorkerPool()
    base_node = WorkerNode(node_id="worker-static-1", max_concurrency=4)
    pool.register_node(base_node)

    autoscaler = WorkerAutoScaler(
        pool=pool,
        min_nodes=1,
        max_nodes=4,
        cooldown_seconds=0.0,
    )

    # Provision 2 auto-scaled nodes
    _ = await autoscaler.evaluate_and_scale(backlog_tasks=5)
    _ = await autoscaler.evaluate_and_scale(backlog_tasks=5)
    assert pool.total_nodes == 3

    # Scale in with zero backlog and low utilization
    event_in1 = await autoscaler.evaluate_and_scale(backlog_tasks=0)
    assert event_in1 is not None
    assert event_in1.direction == ScalingDirection.SCALE_IN
    assert pool.total_nodes == 2

    # Scale in again down to min_nodes
    event_in2 = await autoscaler.evaluate_and_scale(backlog_tasks=0)
    assert event_in2 is not None
    assert event_in2.direction == ScalingDirection.SCALE_IN
    assert pool.total_nodes == 1

    # Scale in floor reached (min_nodes = 1)
    event_floor = await autoscaler.evaluate_and_scale(backlog_tasks=0)
    assert event_floor is None
    assert pool.total_nodes == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_autoscaler_cooldown_suppression() -> None:
    """Verify anti-thrashing cooldown suppresses consecutive scaling actions."""
    pool = DistributedWorkerPool()
    base_node = WorkerNode(node_id="worker-static-1", max_concurrency=4)
    pool.register_node(base_node)

    autoscaler = WorkerAutoScaler(
        pool=pool,
        min_nodes=1,
        max_nodes=4,
        cooldown_seconds=5.0,  # 5 second cooldown
    )

    # First scale-out succeeds
    ev1 = await autoscaler.evaluate_and_scale(backlog_tasks=3)
    assert ev1 is not None
    assert autoscaler.is_in_cooldown is True

    # Immediate next evaluation is suppressed by cooldown
    ev2 = await autoscaler.evaluate_and_scale(backlog_tasks=3)
    assert ev2 is None
    assert pool.total_nodes == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cluster_orchestrator_lifecycle_and_snapshot() -> None:
    """Verify ClusterOrchestrator manages supervisor/autoscaler lifecycle and exports status snapshots."""
    pool = DistributedWorkerPool()
    node = WorkerNode(node_id="worker-orchestrated", max_concurrency=4)
    pool.register_node(node)

    orchestrator = ClusterOrchestrator(
        pool=pool,
        autoscale_interval_seconds=0.1,
    )

    try:
        await orchestrator.start()
        assert orchestrator.is_running is True

        snapshot = orchestrator.get_cluster_snapshot()
        assert snapshot["total_nodes"] == 1
        assert snapshot["healthy_nodes"] == 1
        assert snapshot["total_capacity"] == 4
        assert snapshot["status_breakdown"]["ONLINE"] == 1

        # Signal backlog from scheduler
        scale_ev = await orchestrator.notify_task_backlog(backlog_count=2)
        assert scale_ev is not None
        assert scale_ev.direction == ScalingDirection.SCALE_OUT

        snapshot_updated = orchestrator.get_cluster_snapshot()
        assert snapshot_updated["total_nodes"] == 2
        assert len(snapshot_updated["recent_scaling_events"]) == 1

    finally:
        await orchestrator.stop()
        assert not orchestrator.is_running
