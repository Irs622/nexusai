"""WorkerNode representation and lifecycle management for distributed cluster execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Mapping

from nexusai.brain.domain.observability import sanitize_attributes
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.core.errors import ToolExecutionError


class WorkerNodeStatus(str, Enum):
    """Lifecycle status taxonomy for distributed worker nodes."""

    ONLINE = "ONLINE"
    BUSY = "BUSY"
    DRAINING = "DRAINING"
    OFFLINE = "OFFLINE"


@dataclass
class WorkerMetrics:
    """Operational telemetry and performance metrics for a worker node."""

    total_tasks_executed: int = 0
    active_tasks: int = 0
    failed_tasks: int = 0
    total_execution_time_ms: float = 0.0
    last_heartbeat: float = field(default_factory=time.time)

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average task latency in milliseconds."""
        if self.total_tasks_executed == 0:
            return 0.0
        return round(self.total_execution_time_ms / self.total_tasks_executed, 2)


@dataclass
class WorkerNode:
    """Represents an execution node in the distributed worker cluster."""

    node_id: str
    endpoint: str = "in-process"
    max_concurrency: int = 4
    labels: set[str] = field(default_factory=set)
    capabilities: frozenset[str] = field(default_factory=frozenset)
    status: WorkerNodeStatus = WorkerNodeStatus.ONLINE
    metrics: WorkerMetrics = field(default_factory=WorkerMetrics)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.node_id.strip():
            raise ValueError("node_id cannot be empty")
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self.metadata = sanitize_attributes(self.metadata)

    def can_accept_task(self) -> bool:
        """Check if node is online and has available execution capacity."""
        if self.status != WorkerNodeStatus.ONLINE:
            return False
        return self.metrics.active_tasks < self.max_concurrency

    def drain(self) -> None:
        """Set node to DRAINING status to reject new tasks while finishing active tasks."""
        if self.status != WorkerNodeStatus.OFFLINE:
            self.status = WorkerNodeStatus.DRAINING

    def mark_offline(self) -> None:
        """Mark node as OFFLINE."""
        self.status = WorkerNodeStatus.OFFLINE

    def mark_online(self) -> None:
        """Restore node to ONLINE status if previously draining or offline."""
        self.status = WorkerNodeStatus.ONLINE
        self.metrics.last_heartbeat = time.time()

    async def ping(self) -> bool:
        """Health check ping verifying node responsiveness."""
        if self.status == WorkerNodeStatus.OFFLINE:
            return False
        self.metrics.last_heartbeat = time.time()
        return True

    async def execute(
        self,
        request: ToolExecutionRequest,
        tool_port: IToolPort,
    ) -> ToolExecutionResult:
        """Execute a tool execution request on this worker node."""
        if not self.can_accept_task():
            raise ToolExecutionError(
                f"Worker node '{self.node_id}' cannot accept tasks in status '{self.status.value}'"
                f" (active: {self.metrics.active_tasks}/{self.max_concurrency})"
            )

        self.metrics.active_tasks += 1
        if self.metrics.active_tasks >= self.max_concurrency:
            self.status = WorkerNodeStatus.BUSY

        start_time = time.perf_counter()
        try:
            res = await tool_port.execute(request)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            self.metrics.total_tasks_executed += 1
            self.metrics.total_execution_time_ms += elapsed_ms
            if not res.success:
                self.metrics.failed_tasks += 1

            return res
        except Exception as err:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            self.metrics.total_tasks_executed += 1
            self.metrics.failed_tasks += 1
            self.metrics.total_execution_time_ms += elapsed_ms
            return ToolExecutionResult(
                request_id=request.execution_id or f"exec-{int(time.time()*1000)}",
                tool_name=request.tool_name,
                success=False,
                error_message=str(err),
                execution_time_ms=elapsed_ms,
            )
        finally:
            self.metrics.active_tasks = max(0, self.metrics.active_tasks - 1)
            if self.status == WorkerNodeStatus.BUSY:
                self.status = WorkerNodeStatus.ONLINE
