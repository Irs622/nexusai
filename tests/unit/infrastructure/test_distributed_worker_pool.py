"""Unit tests for DistributedWorkerPool and task routing strategies."""

from __future__ import annotations

import pytest

from nexusai.infrastructure.distributed.pool import DistributedWorkerPool, RoutingStrategy
from nexusai.infrastructure.distributed.worker_node import WorkerNode, WorkerNodeStatus


def test_pool_registration_and_lookup() -> None:
    """Verify worker node registration and deregistration."""
    pool = DistributedWorkerPool()
    node1 = WorkerNode("node-01")
    node2 = WorkerNode("node-02")

    pool.register_node(node1)
    pool.register_node(node2)
    assert pool.total_nodes == 2
    assert pool.get_node("node-01") is node1

    removed = pool.deregister_node("node-01")
    assert removed is node1
    assert pool.total_nodes == 1
    assert pool.get_node("node-01") is None


@pytest.mark.asyncio
async def test_pool_routing_least_busy() -> None:
    """Verify LEAST_BUSY routing strategy prioritizes worker with lowest active load."""
    pool = DistributedWorkerPool(default_strategy=RoutingStrategy.LEAST_BUSY)
    node1 = WorkerNode("node-01", max_concurrency=4)
    node1.metrics.active_tasks = 2

    node2 = WorkerNode("node-02", max_concurrency=4)
    node2.metrics.active_tasks = 0

    node3 = WorkerNode("node-03", max_concurrency=4)
    node3.metrics.active_tasks = 1

    pool.register_node(node1)
    pool.register_node(node2)
    pool.register_node(node3)

    selected = await pool.select_node()
    assert selected is not None
    assert selected.node_id == "node-02"


@pytest.mark.asyncio
async def test_pool_routing_round_robin() -> None:
    """Verify ROUND_ROBIN routing strategy cycles evenly across healthy nodes."""
    pool = DistributedWorkerPool(default_strategy=RoutingStrategy.ROUND_ROBIN)
    node1 = WorkerNode("node-01", max_concurrency=4)
    node2 = WorkerNode("node-02", max_concurrency=4)
    pool.register_node(node1)
    pool.register_node(node2)

    sel1 = await pool.select_node()
    sel2 = await pool.select_node()
    sel3 = await pool.select_node()

    assert sel1 is not None and sel2 is not None and sel3 is not None
    assert sel1.node_id == "node-01"
    assert sel2.node_id == "node-02"
    assert sel3.node_id == "node-01"


@pytest.mark.asyncio
async def test_pool_routing_capability_match() -> None:
    """Verify CAPABILITY_MATCH filters nodes to only those possessing requested capabilities."""
    pool = DistributedWorkerPool()
    node_general = WorkerNode("node-gen", capabilities=frozenset({"FILE_READ"}))
    node_gpu = WorkerNode("node-gpu", capabilities=frozenset({"FILE_READ", "LLM_INFERENCE"}))

    pool.register_node(node_general)
    pool.register_node(node_gpu)

    # Request LLM_INFERENCE capability -> only node-gpu matches
    selected = await pool.select_node(required_capabilities=frozenset({"LLM_INFERENCE"}))
    assert selected is not None
    assert selected.node_id == "node-gpu"


@pytest.mark.asyncio
async def test_pool_drain_node_removes_from_selection() -> None:
    """Verify draining a node excludes it from task selection."""
    pool = DistributedWorkerPool()
    node1 = WorkerNode("node-01")
    node2 = WorkerNode("node-02")
    pool.register_node(node1)
    pool.register_node(node2)

    assert pool.drain_node("node-01") is True
    assert node1.status == WorkerNodeStatus.DRAINING

    # Now select should always pick node-02
    selected = await pool.select_node()
    assert selected is not None
    assert selected.node_id == "node-02"


@pytest.mark.asyncio
async def test_pool_health_check_all() -> None:
    """Verify health_check_all checks all nodes."""
    pool = DistributedWorkerPool()
    node1 = WorkerNode("node-01")
    node2 = WorkerNode("node-02")
    node2.mark_offline()

    pool.register_node(node1)
    pool.register_node(node2)

    results = await pool.health_check_all()
    assert results == {"node-01": True, "node-02": False}


def test_pool_from_config_dict() -> None:
    """Verify pool instantiation from configuration dictionary."""
    config = {
        "default_strategy": "ROUND_ROBIN",
        "workers": [
            {
                "node_id": "cfg-worker-1",
                "endpoint": "http://127.0.0.1:8081",
                "max_concurrency": 6,
                "labels": ["tier-1"],
                "capabilities": ["FILE_READ"],
            },
            {
                "node_id": "cfg-worker-2",
                "endpoint": "http://127.0.0.1:8082",
                "max_concurrency": 2,
            },
        ],
    }

    pool = DistributedWorkerPool.from_config_dict(config)
    assert pool.total_nodes == 2
    assert pool.default_strategy == RoutingStrategy.ROUND_ROBIN
    w1 = pool.get_node("cfg-worker-1")
    assert w1 is not None
    assert w1.max_concurrency == 6
    assert "FILE_READ" in w1.capabilities
