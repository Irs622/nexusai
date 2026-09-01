"""DistributedWorkerPool managing cluster worker nodes and routing strategies."""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Mapping

from nexusai.infrastructure.distributed.worker_node import WorkerNode, WorkerNodeStatus


class RoutingStrategy(str, Enum):
    """Routing strategies for distributing tasks across worker nodes."""

    LEAST_BUSY = "LEAST_BUSY"
    ROUND_ROBIN = "ROUND_ROBIN"
    CAPABILITY_MATCH = "CAPABILITY_MATCH"


class DistributedWorkerPool:
    """Pool manager maintaining active worker nodes and intelligent task routing."""

    def __init__(self, default_strategy: RoutingStrategy = RoutingStrategy.LEAST_BUSY) -> None:
        self._nodes: dict[str, WorkerNode] = {}
        self.default_strategy = default_strategy
        self._round_robin_index = 0
        self._lock = asyncio.Lock()

    @property
    def total_nodes(self) -> int:
        """Return total registered worker nodes."""
        return len(self._nodes)

    def register_node(self, node: WorkerNode) -> None:
        """Register a worker node in the cluster pool."""
        self._nodes[node.node_id] = node

    def deregister_node(self, node_id: str) -> WorkerNode | None:
        """Remove a worker node from the cluster pool."""
        return self._nodes.pop(node_id, None)

    def get_node(self, node_id: str) -> WorkerNode | None:
        """Retrieve a worker node by its ID."""
        return self._nodes.get(node_id)

    def get_healthy_nodes(self) -> list[WorkerNode]:
        """Return all nodes in ONLINE status capable of accepting tasks."""
        return [node for node in self._nodes.values() if node.status == WorkerNodeStatus.ONLINE]

    async def select_node(
        self,
        strategy: RoutingStrategy | None = None,
        required_capabilities: frozenset[str] | None = None,
    ) -> WorkerNode | None:
        """Select the best available worker node based on requested routing strategy and capabilities."""
        strat = strategy or self.default_strategy
        candidates = self.get_healthy_nodes()

        if not candidates:
            return None

        # Filter by required capabilities if specified
        if required_capabilities:
            matching = [n for n in candidates if required_capabilities.issubset(n.capabilities)]
            if matching:
                candidates = matching

        # Filter to nodes that currently have available capacity
        available = [n for n in candidates if n.can_accept_task()]
        if not available:
            return None

        async with self._lock:
            if strat == RoutingStrategy.ROUND_ROBIN:
                node = available[self._round_robin_index % len(available)]
                self._round_robin_index = (self._round_robin_index + 1) % len(available)
                return node

            # Default: LEAST_BUSY (lowest active task count, tie-break on avg latency)
            available.sort(key=lambda n: (n.metrics.active_tasks, n.metrics.avg_latency_ms))
            return available[0]

    def drain_node(self, node_id: str) -> bool:
        """Initiate graceful draining on specified worker node."""
        node = self.get_node(node_id)
        if node:
            node.drain()
            return True
        return False

    async def health_check_all(self) -> dict[str, bool]:
        """Run health checks across all registered worker nodes."""
        results: dict[str, bool] = {}
        for node_id, node in self._nodes.items():
            results[node_id] = await node.ping()
        return results

    @classmethod
    def from_config_dict(cls, config: Mapping[str, Any]) -> DistributedWorkerPool:
        """Instantiate DistributedWorkerPool from parsed configuration dictionary."""
        strategy_str = config.get("default_strategy", "LEAST_BUSY")
        strategy = RoutingStrategy(strategy_str)
        pool = cls(default_strategy=strategy)

        nodes_data = config.get("workers", [])
        for item in nodes_data:
            node = WorkerNode(
                node_id=item["node_id"],
                endpoint=item.get("endpoint", "in-process"),
                max_concurrency=item.get("max_concurrency", 4),
                labels=set(item.get("labels", [])),
                capabilities=frozenset(item.get("capabilities", [])),
            )
            pool.register_node(node)

        return pool
