"""
Runtime Dependency Graph manager for NexusAI OS Kernel services.
"""

from __future__ import annotations

from collections import deque
from typing import Sequence

from nexusai.core.errors import DependencyCycleError, GraphFrozenError, MissingDependencyError
from nexusai.kernel.contracts import KernelService, ServiceDescriptor
from nexusai.logging.logger import logger


class RuntimeDependencyGraph:
    """Directed Acyclic Graph (DAG) for kernel service boot and shutdown ordering."""

    def __init__(self) -> None:
        self._descriptors: dict[str, ServiceDescriptor] = {}
        self._frozen: bool = False
        self._cached_boot_order: tuple[str, ...] | None = None

    @property
    def is_frozen(self) -> bool:
        """Return True if the dependency graph is frozen and immutable."""
        return self._frozen

    def add_service(self, service_or_descriptor: KernelService | ServiceDescriptor) -> None:
        """Add a service or descriptor to the dependency graph.

        Raises:
            GraphFrozenError: If graph is frozen.
        """
        if self._frozen:
            raise GraphFrozenError("Cannot modify dependency graph after it has been frozen.")

        descriptor = (
            service_or_descriptor.descriptor
            if isinstance(service_or_descriptor, KernelService)
            else service_or_descriptor
        )
        self._descriptors[descriptor.id] = descriptor
        self._cached_boot_order = None

    def validate(self) -> None:
        """Validate dependency graph for missing dependencies and cycles.

        Raises:
            MissingDependencyError: If a service references a dependency not in the graph.
            DependencyCycleError: If a circular dependency is detected.
        """
        # 1. Check for missing dependencies
        for s_id, descriptor in self._descriptors.items():
            for dep_id in descriptor.dependencies:
                if dep_id not in self._descriptors:
                    raise MissingDependencyError(
                        f"Service '{s_id}' requires missing dependency '{dep_id}'."
                    )

        # 2. Compute boot order to detect cycles via Kahn's algorithm
        self._compute_topological_boot_order()

    def freeze(self) -> None:
        """Validate and freeze the dependency graph, rendering it immutable."""
        if not self._frozen:
            self.validate()
            self._frozen = True
            logger.info("RuntimeDependencyGraph has been validated and frozen.")

    def get_startup_order(self) -> tuple[str, ...]:
        """Return the topological boot order of service IDs.

        If not frozen, graph is validated and topological order is computed.
        """
        if self._cached_boot_order is not None:
            return self._cached_boot_order

        boot_order = self._compute_topological_boot_order()
        if self._frozen:
            self._cached_boot_order = boot_order
        return boot_order

    def get_shutdown_order(self) -> tuple[str, ...]:
        """Return the reverse topological shutdown order of service IDs."""
        startup_order = self.get_startup_order()
        return tuple(reversed(startup_order))

    def _compute_topological_boot_order(self) -> tuple[str, ...]:
        """Compute topological order using Kahn's algorithm."""
        in_degree: dict[str, int] = {s_id: 0 for s_id in self._descriptors}
        graph: dict[str, list[str]] = {s_id: [] for s_id in self._descriptors}

        # Build adjacency graph: dep -> service (dep must start BEFORE service)
        for s_id, descriptor in self._descriptors.items():
            for dep_id in descriptor.dependencies:
                if dep_id in self._descriptors:
                    graph[dep_id].append(s_id)
                    in_degree[s_id] += 1

        # Queue nodes with in-degree 0 (no dependencies)
        queue: deque[str] = deque([s_id for s_id, deg in in_degree.items() if deg == 0])
        boot_order: list[str] = []

        while queue:
            node = queue.popleft()
            boot_order.append(node)

            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(boot_order) != len(self._descriptors):
            # Nodes remaining with in_degree > 0 are part of a cycle
            cycle_nodes = [s_id for s_id, deg in in_degree.items() if deg > 0]
            raise DependencyCycleError(
                f"Circular dependency detected among kernel services: {cycle_nodes}"
            )

        return tuple(boot_order)
