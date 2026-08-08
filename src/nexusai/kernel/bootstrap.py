"""
Kernel Bootstrap helper for wiring DI Container, Service Registry, and Dependency Graph.
"""

from __future__ import annotations

from typing import Sequence

from nexusai.core.config import SystemConfig
from nexusai.core.container import DependencyContainer
from nexusai.kernel.contracts import KernelService
from nexusai.kernel.dependency_graph import RuntimeDependencyGraph
from nexusai.kernel.registry import ServiceRegistry
from nexusai.logging.logger import logger


class KernelBootstrap:
    """Helper class to bootstrap kernel dependencies, register services, and validate graph invariants."""

    def __init__(
        self,
        config: SystemConfig | None = None,
        container: DependencyContainer | None = None,
        registry: ServiceRegistry | None = None,
        dependency_graph: RuntimeDependencyGraph | None = None,
    ) -> None:
        self.config = config or SystemConfig()
        self.container = container or DependencyContainer()
        self.registry = registry or ServiceRegistry()
        self.dependency_graph = dependency_graph or RuntimeDependencyGraph()

    def register_service(self, service: KernelService) -> None:
        """Register a KernelService into both the ServiceRegistry and RuntimeDependencyGraph."""
        self.registry.register(service)
        self.dependency_graph.add_service(service)

    def register_services(self, services: Sequence[KernelService]) -> None:
        """Register multiple services in batch."""
        for service in services:
            self.register_service(service)

    def prepare_container(self) -> DependencyContainer:
        """Register standard kernel abstractions in DI Container."""
        if hasattr(self.container, "_frozen"):
            self.container._frozen = False
        try:
            self.container.register_singleton(SystemConfig, self.config)
            self.container.register_singleton(ServiceRegistry, self.registry)
            self.container.register_singleton(RuntimeDependencyGraph, self.dependency_graph)
        except Exception:
            pass
        return self.container

    def validate_and_freeze(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Validate and freeze the dependency graph.

        Returns:
            Tuple of (boot_order_ids, shutdown_order_ids)
        """
        logger.info("Bootstrapping kernel dependency graph...")
        if hasattr(self.dependency_graph, "_frozen"):
            self.dependency_graph._frozen = False
        self.dependency_graph.freeze()
        boot_order = self.dependency_graph.get_startup_order()
        shutdown_order = self.dependency_graph.get_shutdown_order()
        logger.info(f"Kernel boot sequence resolved: {boot_order}")
        return boot_order, shutdown_order
