"""Unit tests for WorkerNode representation, state transitions, and execution telemetry."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.core.errors import ToolExecutionError
from nexusai.infrastructure.distributed.worker_node import (
    WorkerNode,
    WorkerNodeStatus,
)


@pytest.fixture
def mock_tool_port() -> IToolPort:
    port = AsyncMock(spec=IToolPort)
    port.execute.return_value = ToolExecutionResult(
        request_id="req-1",
        tool_name="test_tool",
        success=True,
        result_data="SUCCESS",
        execution_time_ms=10.0,
    )
    return port


def test_worker_node_initialization_and_validation() -> None:
    """Verify WorkerNode attributes and validation invariants."""
    node = WorkerNode(
        node_id="worker-01",
        endpoint="http://10.0.0.1:8080",
        max_concurrency=4,
        labels={"tier-1"},
        capabilities=frozenset({"FILE_READ"}),
    )
    assert node.node_id == "worker-01"
    assert node.endpoint == "http://10.0.0.1:8080"
    assert node.status == WorkerNodeStatus.ONLINE
    assert node.can_accept_task() is True

    with pytest.raises(ValueError, match="node_id cannot be empty"):
        WorkerNode(node_id="")

    with pytest.raises(ValueError, match="max_concurrency must be at least 1"):
        WorkerNode(node_id="worker-02", max_concurrency=0)


def test_worker_node_status_transitions() -> None:
    """Verify node status transitions: drain, offline, and restore online."""
    node_drain = WorkerNode(node_id="worker-01", max_concurrency=2)
    node_drain.drain()
    assert node_drain.status.value == "DRAINING"
    assert node_drain.can_accept_task() is False

    node_offline = WorkerNode(node_id="worker-02", max_concurrency=2)
    node_offline.mark_offline()
    assert node_offline.status.value == "OFFLINE"
    assert node_offline.can_accept_task() is False

    node_restore = WorkerNode(node_id="worker-03", max_concurrency=2)
    node_restore.drain()
    node_restore.mark_online()
    assert node_restore.status.value == "ONLINE"
    assert node_restore.can_accept_task() is True


@pytest.mark.asyncio
async def test_worker_node_ping_and_health() -> None:
    """Verify ping responsiveness and heartbeat updating."""
    node = WorkerNode(node_id="worker-01")
    assert await node.ping() is True

    node.mark_offline()
    assert await node.ping() is False


@pytest.mark.asyncio
async def test_worker_node_execute_success_and_metrics(mock_tool_port: IToolPort) -> None:
    """Verify task execution updates active counts, latency, and totals."""
    node = WorkerNode(node_id="worker-01", max_concurrency=2)
    req = ToolExecutionRequest("test_tool", {"param": 1}, execution_id="req-101")

    res = await node.execute(req, mock_tool_port)

    assert res.success is True
    assert res.result_data == "SUCCESS"
    assert node.metrics.total_tasks_executed == 1
    assert node.metrics.failed_tasks == 0
    assert node.metrics.active_tasks == 0
    assert node.metrics.avg_latency_ms >= 0.0


@pytest.mark.asyncio
async def test_worker_node_execute_rejects_when_full(mock_tool_port: IToolPort) -> None:
    """Verify execute raises ToolExecutionError when node has reached max concurrency."""
    node = WorkerNode(node_id="worker-01", max_concurrency=1)
    node.metrics.active_tasks = 1  # artificially fill

    req = ToolExecutionRequest("test_tool", {}, execution_id="req-102")
    with pytest.raises(ToolExecutionError, match="cannot accept tasks"):
        await node.execute(req, mock_tool_port)


@pytest.mark.asyncio
async def test_worker_node_execute_failure_metrics() -> None:
    """Verify failed tool execution increments failure metrics."""
    failing_port = AsyncMock(spec=IToolPort)
    failing_port.execute.return_value = ToolExecutionResult(
        request_id="req-fail",
        tool_name="fail_tool",
        success=False,
        error_message="Execution timeout",
    )

    node = WorkerNode(node_id="worker-01", max_concurrency=2)
    req = ToolExecutionRequest("fail_tool", {}, execution_id="req-fail")

    res = await node.execute(req, failing_port)
    assert res.success is False
    assert node.metrics.total_tasks_executed == 1
    assert node.metrics.failed_tasks == 1
    assert node.metrics.active_tasks == 0
