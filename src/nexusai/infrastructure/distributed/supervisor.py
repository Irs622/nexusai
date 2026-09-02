"""Heartbeat Supervisor managing health monitoring, dead node eviction, and auto-recovery for worker clusters."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import time

from nexusai.infrastructure.distributed.pool import DistributedWorkerPool
from nexusai.infrastructure.distributed.worker_node import WorkerNode, WorkerNodeStatus
from nexusai.logging.logger import logger

NodeEventCallback = Callable[[WorkerNode], Awaitable[None] | None]


@dataclass
class NodeHealthTracker:
    """Tracks consecutive health check outcomes and status history for an individual worker node."""

    node_id: str
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_ping_time: float = field(default_factory=time.time)
    last_ping_latency_ms: float = 0.0
    is_evicted: bool = False


class WorkerHeartbeatSupervisor:
    """Periodically supervises worker node heartbeats, evicts unresponsive nodes, and auto-recovers revived nodes."""

    def __init__(
        self,
        pool: DistributedWorkerPool,
        check_interval_seconds: float = 1.0,
        heartbeat_timeout_seconds: float = 2.0,
        max_consecutive_failures: int = 3,
        recovery_threshold: int = 2,
        on_node_evicted: NodeEventCallback | None = None,
        on_node_recovered: NodeEventCallback | None = None,
    ) -> None:
        self.pool = pool
        self.check_interval_seconds = check_interval_seconds
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self.max_consecutive_failures = max_consecutive_failures
        self.recovery_threshold = recovery_threshold
        self.on_node_evicted = on_node_evicted
        self.on_node_recovered = on_node_recovered

        self._trackers: dict[str, NodeHealthTracker] = {}
        self._loop_task: asyncio.Task[None] | None = None
        self._is_running = False
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        """Return True if background supervision loop is active."""
        return self._is_running and self._loop_task is not None and not self._loop_task.done()

    def get_tracker(self, node_id: str) -> NodeHealthTracker:
        """Get or initialize health tracker for specified node."""
        if node_id not in self._trackers:
            self._trackers[node_id] = NodeHealthTracker(node_id=node_id)
        return self._trackers[node_id]

    async def start(self) -> None:
        """Start the background periodic heartbeat supervisor loop."""
        async with self._lock:
            if self.is_running:
                return
            self._is_running = True
            self._loop_task = asyncio.create_task(self._supervision_loop())
            logger.info(
                f"[WorkerHeartbeatSupervisor] Started supervision loop (interval: {self.check_interval_seconds}s)"
            )

    async def stop(self) -> None:
        """Gracefully stop the background supervision loop."""
        async with self._lock:
            self._is_running = False
            if self._loop_task and not self._loop_task.done():
                self._loop_task.cancel()
                try:
                    await self._loop_task
                except asyncio.CancelledError:
                    pass
                self._loop_task = None
            logger.info("[WorkerHeartbeatSupervisor] Stopped supervision loop")

    async def check_node(self, node: WorkerNode) -> bool:
        """Check a single node's health, updating its tracker and triggering eviction or recovery if needed."""
        tracker = self.get_tracker(node.node_id)
        start_time = time.perf_counter()
        is_healthy = False

        try:
            is_healthy = await asyncio.wait_for(
                node.ping(), timeout=self.heartbeat_timeout_seconds
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            tracker.last_ping_latency_ms = round(elapsed_ms, 2)
            tracker.last_ping_time = time.time()
        except (asyncio.TimeoutError, Exception) as err:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            tracker.last_ping_latency_ms = round(elapsed_ms, 2)
            logger.warning(
                f"[WorkerHeartbeatSupervisor] Ping failed for node '{node.node_id}': {err}"
            )
            is_healthy = False

        if is_healthy:
            tracker.consecutive_successes += 1
            tracker.consecutive_failures = 0

            # Check for auto-recovery if previously evicted or offline
            if tracker.is_evicted or node.status in (
                WorkerNodeStatus.OFFLINE,
                WorkerNodeStatus.DRAINING,
            ):
                if tracker.consecutive_successes >= self.recovery_threshold:
                    tracker.is_evicted = False
                    node.mark_online()
                    logger.info(
                        f"[WorkerHeartbeatSupervisor] Auto-recovered node '{node.node_id}' back to ONLINE"
                    )
                    if self.on_node_recovered:
                        cb_res = self.on_node_recovered(node)
                        if asyncio.iscoroutine(cb_res):
                            await cb_res
        else:
            tracker.consecutive_failures += 1
            tracker.consecutive_successes = 0

            # Check for eviction
            if (
                not tracker.is_evicted
                and tracker.consecutive_failures >= self.max_consecutive_failures
            ):
                tracker.is_evicted = True
                node.mark_offline()
                logger.error(
                    f"[WorkerHeartbeatSupervisor] Node '{node.node_id}' evicted after "
                    f"{tracker.consecutive_failures} consecutive ping failures -> OFFLINE"
                )
                if self.on_node_evicted:
                    cb_res = self.on_node_evicted(node)
                    if asyncio.iscoroutine(cb_res):
                        await cb_res

        return is_healthy

    async def check_all_nodes(self) -> dict[str, bool]:
        """Perform a single round of health checks across all nodes registered in the pool."""
        results: dict[str, bool] = {}
        # Snapshot nodes dict to avoid concurrent mutation issues
        nodes = list(self.pool._nodes.values())
        for node in nodes:
            results[node.node_id] = await self.check_node(node)
        return results

    async def _supervision_loop(self) -> None:
        """Background loop executing health checks at specified intervals."""
        while self._is_running:
            try:
                await self.check_all_nodes()
            except Exception as loop_err:
                logger.error(f"[WorkerHeartbeatSupervisor] Error in supervision round: {loop_err}")

            try:
                await asyncio.sleep(self.check_interval_seconds)
            except asyncio.CancelledError:
                break
