"""ClusterOrchestrator coordinating worker pool, heartbeat supervisor, and auto-scaler."""

from __future__ import annotations

import asyncio
from typing import Any

from nexusai.infrastructure.distributed.autoscaler import (
    ScalingEvent,
    WorkerAutoScaler,
)
from nexusai.infrastructure.distributed.pool import DistributedWorkerPool
from nexusai.infrastructure.distributed.supervisor import WorkerHeartbeatSupervisor
from nexusai.infrastructure.distributed.worker_node import WorkerNodeStatus
from nexusai.logging.logger import logger


class ClusterOrchestrator:
    """Unified coordinator managing cluster topology, health supervision, and elastic auto-scaling."""

    def __init__(
        self,
        pool: DistributedWorkerPool,
        supervisor: WorkerHeartbeatSupervisor | None = None,
        autoscaler: WorkerAutoScaler | None = None,
        autoscale_interval_seconds: float = 2.0,
    ) -> None:
        self.pool = pool
        self.supervisor = supervisor or WorkerHeartbeatSupervisor(pool=self.pool)
        self.autoscaler = autoscaler or WorkerAutoScaler(pool=self.pool)
        self.autoscale_interval_seconds = autoscale_interval_seconds

        self._autoscale_task: asyncio.Task[None] | None = None
        self._is_running = False
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        """Return True if cluster supervisor and auto-scaler are active."""
        return self._is_running and self.supervisor.is_running

    async def start(self) -> None:
        """Start both the heartbeat supervisor and periodic auto-scaler evaluation loops."""
        async with self._lock:
            if self.is_running:
                return
            self._is_running = True
            await self.supervisor.start()
            self._autoscale_task = asyncio.create_task(self._autoscale_loop())
            logger.info("[ClusterOrchestrator] Cluster supervision and auto-scaling active")

    async def stop(self) -> None:
        """Gracefully stop supervision and auto-scaler loops."""
        async with self._lock:
            self._is_running = False
            await self.supervisor.stop()
            if self._autoscale_task and not self._autoscale_task.done():
                self._autoscale_task.cancel()
                try:
                    await self._autoscale_task
                except asyncio.CancelledError:
                    pass
                self._autoscale_task = None
            logger.info("[ClusterOrchestrator] Cluster supervision and auto-scaling stopped")

    async def _autoscale_loop(self) -> None:
        """Periodic background loop evaluating cluster scaling needs."""
        while self._is_running:
            try:
                await self.autoscaler.evaluate_and_scale(backlog_tasks=0)
            except Exception as e:
                logger.error(f"[ClusterOrchestrator] Error during auto-scaling evaluation: {e}")

            try:
                await asyncio.sleep(self.autoscale_interval_seconds)
            except asyncio.CancelledError:
                break

    async def notify_task_backlog(self, backlog_count: int) -> ScalingEvent | None:
        """Directly signal task backlog pressure from scheduler to trigger immediate scaling evaluation."""
        return await self.autoscaler.evaluate_and_scale(backlog_tasks=backlog_count)

    def get_cluster_snapshot(self) -> dict[str, Any]:
        """Generate structured cluster health and capacity snapshot for telemetri & dashboard."""
        metrics = self.autoscaler.calculate_metrics()
        nodes = list(self.pool._nodes.values())

        status_counts = {
            WorkerNodeStatus.ONLINE.value: 0,
            WorkerNodeStatus.BUSY.value: 0,
            WorkerNodeStatus.DRAINING.value: 0,
            WorkerNodeStatus.OFFLINE.value: 0,
        }
        for n in nodes:
            status_counts[n.status.value] = status_counts.get(n.status.value, 0) + 1

        recent_events = [
            {
                "timestamp": ev.timestamp,
                "direction": ev.direction.value,
                "target_node": ev.target_node_id,
                "reason": ev.reason,
                "nodes_before": ev.active_nodes_before,
                "nodes_after": ev.active_nodes_after,
            }
            for ev in self.autoscaler.get_scaling_history(limit=5)
        ]

        return {
            "total_nodes": metrics.total_nodes,
            "healthy_nodes": metrics.healthy_nodes,
            "total_capacity": metrics.total_capacity,
            "active_tasks": metrics.active_tasks,
            "utilization_ratio": metrics.utilization_ratio,
            "status_breakdown": status_counts,
            "auto_scaled_nodes_count": len(self.autoscaler._auto_scaled_node_ids),
            "recent_scaling_events": recent_events,
        }
