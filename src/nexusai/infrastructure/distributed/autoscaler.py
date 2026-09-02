"""Autonomous Worker Auto-Scaler providing elastic capacity management for distributed DAG workloads."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
import time

from nexusai.infrastructure.distributed.pool import DistributedWorkerPool
from nexusai.infrastructure.distributed.worker_node import WorkerNode
from nexusai.logging.logger import logger


class ScalingDirection(str, Enum):
    """Direction of an auto-scaling action."""

    SCALE_OUT = "SCALE_OUT"
    SCALE_IN = "SCALE_IN"
    NONE = "NONE"


@dataclass(frozen=True)
class ScalingEvent:
    """Telemetry record of a scaling decision and action."""

    timestamp: float = field(default_factory=time.time)
    direction: ScalingDirection = ScalingDirection.NONE
    target_node_id: str = ""
    reason: str = ""
    active_nodes_before: int = 0
    active_nodes_after: int = 0
    utilization_before: float = 0.0


@dataclass(frozen=True)
class ClusterMetrics:
    """Aggregated real-time metrics of cluster load and capacity."""

    total_nodes: int
    healthy_nodes: int
    total_capacity: int
    active_tasks: int
    utilization_ratio: float
    backlog_tasks: int


class WorkerAutoScaler:
    """Dynamically scales worker node pool size based on task queue pressure and cluster utilization."""

    def __init__(
        self,
        pool: DistributedWorkerPool,
        min_nodes: int = 1,
        max_nodes: int = 8,
        scale_up_utilization_threshold: float = 0.8,
        scale_down_utilization_threshold: float = 0.2,
        cooldown_seconds: float = 5.0,
        default_node_concurrency: int = 4,
        node_factory: Callable[[str], WorkerNode] | None = None,
    ) -> None:
        self.pool = pool
        self.min_nodes = max(1, min_nodes)
        self.max_nodes = max(self.min_nodes, max_nodes)
        self.scale_up_utilization_threshold = scale_up_utilization_threshold
        self.scale_down_utilization_threshold = scale_down_utilization_threshold
        self.cooldown_seconds = cooldown_seconds
        self.default_node_concurrency = default_node_concurrency
        self.node_factory = node_factory or self._default_node_factory

        self._auto_scaled_node_ids: set[str] = set()
        self._scaling_history: list[ScalingEvent] = []
        self._last_scaling_time: float = 0.0
        self._scale_counter = 0
        self._lock = asyncio.Lock()

    def _default_node_factory(self, node_id: str) -> WorkerNode:
        """Create a standard in-process worker node."""
        return WorkerNode(
            node_id=node_id,
            endpoint="in-process",
            max_concurrency=self.default_node_concurrency,
            labels={"auto-scaled", "dynamic"},
            capabilities=frozenset({"general", "computation"}),
        )

    def calculate_metrics(self, backlog_tasks: int = 0) -> ClusterMetrics:
        """Compute aggregated capacity, active workloads, and utilization ratio across healthy nodes."""
        healthy_nodes = self.pool.get_healthy_nodes()
        total_nodes = self.pool.total_nodes
        healthy_count = len(healthy_nodes)

        total_capacity = sum(n.max_concurrency for n in healthy_nodes)
        active_tasks = sum(n.metrics.active_tasks for n in healthy_nodes)

        if total_capacity > 0:
            utilization = round(active_tasks / total_capacity, 3)
        else:
            utilization = 1.0 if (active_tasks > 0 or backlog_tasks > 0) else 0.0

        return ClusterMetrics(
            total_nodes=total_nodes,
            healthy_nodes=healthy_count,
            total_capacity=total_capacity,
            active_tasks=active_tasks,
            utilization_ratio=utilization,
            backlog_tasks=backlog_tasks,
        )

    @property
    def is_in_cooldown(self) -> bool:
        """Return True if cooldown timer is active preventing scale thrashing."""
        return (time.time() - self._last_scaling_time) < self.cooldown_seconds

    async def evaluate_and_scale(self, backlog_tasks: int = 0) -> ScalingEvent | None:
        """Evaluate cluster demand against thresholds and execute scale-out or scale-in if warranted."""
        async with self._lock:
            metrics = self.calculate_metrics(backlog_tasks=backlog_tasks)
            now = time.time()

            # 1. Scale-Out Check (High workload pressure or pending task backlog)
            should_scale_out = (
                backlog_tasks > 0
                or metrics.utilization_ratio >= self.scale_up_utilization_threshold
            )

            if should_scale_out:
                if metrics.healthy_nodes >= self.max_nodes:
                    logger.debug(
                        f"[WorkerAutoScaler] Scale-out requested but max_nodes limit reached ({self.max_nodes})"
                    )
                    return None

                if self.is_in_cooldown:
                    logger.debug("[WorkerAutoScaler] Scale-out suppressed by cooldown guard")
                    return None

                # Execute Scale-Out
                self._scale_counter += 1
                new_node_id = f"worker-auto-{self._scale_counter:03d}"
                new_node = self.node_factory(new_node_id)
                self.pool.register_node(new_node)
                self._auto_scaled_node_ids.add(new_node_id)
                self._last_scaling_time = now

                event = ScalingEvent(
                    timestamp=now,
                    direction=ScalingDirection.SCALE_OUT,
                    target_node_id=new_node_id,
                    reason=(
                        f"Backlog ({backlog_tasks}) or utilization "
                        f"({metrics.utilization_ratio*100:.1f}%) >= {self.scale_up_utilization_threshold*100:.0f}%"
                    ),
                    active_nodes_before=metrics.healthy_nodes,
                    active_nodes_after=metrics.healthy_nodes + 1,
                    utilization_before=metrics.utilization_ratio,
                )
                self._scaling_history.append(event)
                logger.info(
                    f"[WorkerAutoScaler] SCALE-OUT: Added '{new_node_id}' "
                    f"(nodes: {event.active_nodes_before} -> {event.active_nodes_after})"
                )
                return event

            # 2. Scale-In Check (Low utilization, zero backlog, and above min_nodes)
            should_scale_in = (
                backlog_tasks == 0
                and metrics.utilization_ratio <= self.scale_down_utilization_threshold
                and metrics.healthy_nodes > self.min_nodes
                and bool(self._auto_scaled_node_ids)
            )

            if should_scale_in:
                if self.is_in_cooldown:
                    logger.debug("[WorkerAutoScaler] Scale-in suppressed by cooldown guard")
                    return None

                # Find candidate auto-scaled node with zero active tasks
                candidate_id: str | None = None
                for node_id in list(self._auto_scaled_node_ids):
                    node = self.pool.get_node(node_id)
                    if node and node.metrics.active_tasks == 0:
                        candidate_id = node_id
                        break

                if not candidate_id:
                    logger.debug("[WorkerAutoScaler] No idle auto-scaled worker found for scale-in")
                    return None

                # Execute Scale-In (Graceful removal)
                self.pool.deregister_node(candidate_id)
                self._auto_scaled_node_ids.remove(candidate_id)
                self._last_scaling_time = now

                event = ScalingEvent(
                    timestamp=now,
                    direction=ScalingDirection.SCALE_IN,
                    target_node_id=candidate_id,
                    reason=(
                        f"Zero backlog and utilization ({metrics.utilization_ratio*100:.1f}%) "
                        f"<= {self.scale_down_utilization_threshold*100:.0f}%"
                    ),
                    active_nodes_before=metrics.healthy_nodes,
                    active_nodes_after=metrics.healthy_nodes - 1,
                    utilization_before=metrics.utilization_ratio,
                )
                self._scaling_history.append(event)
                logger.info(
                    f"[WorkerAutoScaler] SCALE-IN: Removed idle '{candidate_id}' "
                    f"(nodes: {event.active_nodes_before} -> {event.active_nodes_after})"
                )
                return event

            return None

    def get_scaling_history(self, limit: int = 50) -> list[ScalingEvent]:
        """Return recent scaling events."""
        return self._scaling_history[-limit:]
