"""
Kernel Orchestrator Facade for NexusAI OS Kernel.
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence

from nexusai import __version__ as NEXUSAI_VERSION
from nexusai.core.config import SystemConfig
from nexusai.core.container import DependencyContainer
from nexusai.kernel.bootstrap import KernelBootstrap
from nexusai.kernel.contracts import KernelService
from nexusai.kernel.dependency_graph import RuntimeDependencyGraph
from nexusai.kernel.lifecycle import LifecycleCoordinator
from nexusai.kernel.registry import ServiceRegistry
from nexusai.kernel.scheduler import RuntimeScheduler
from nexusai.kernel.snapshot import KernelSnapshot, SnapshotManager
from nexusai.kernel.worker import BackgroundWorkerManager
from nexusai.logging.logger import logger


class KernelOrchestrator:
    """Facade orchestrating OS Kernel subsystems, lifecycle transitions, schedulers, and metrics aggregation.

    Delegates responsibility to single-purpose components:
    - ServiceRegistry
    - RuntimeDependencyGraph
    - LifecycleCoordinator
    - RuntimeScheduler
    - BackgroundWorkerManager
    - SnapshotManager
    """

    def __init__(
        self,
        config: SystemConfig | None = None,
        container: DependencyContainer | None = None,
        registry: ServiceRegistry | None = None,
        dependency_graph: RuntimeDependencyGraph | None = None,
        lifecycle_coordinator: LifecycleCoordinator | None = None,
        scheduler: RuntimeScheduler | None = None,
        worker_manager: BackgroundWorkerManager | None = None,
        snapshot_manager: SnapshotManager | None = None,
    ) -> None:
        self._bootstrap = KernelBootstrap(
            config=config,
            container=container,
            registry=registry,
            dependency_graph=dependency_graph,
        )
        self.lifecycle = lifecycle_coordinator or LifecycleCoordinator()
        self.scheduler = scheduler or RuntimeScheduler()
        self.worker_manager = worker_manager or BackgroundWorkerManager()
        self.snapshot_manager = snapshot_manager or SnapshotManager(kernel_version=NEXUSAI_VERSION)

        self._boot_id: str | None = None
        self._is_running: bool = False

    @property
    def boot_id(self) -> str | None:
        """Return unique boot ID generated for the current kernel session."""
        return self._boot_id

    @property
    def is_running(self) -> bool:
        """Return True if kernel is booted and currently running."""
        return self._is_running

    @property
    def registry(self) -> ServiceRegistry:
        """Access the underlying ServiceRegistry."""
        return self._bootstrap.registry

    @property
    def dependency_graph(self) -> RuntimeDependencyGraph:
        """Access the underlying RuntimeDependencyGraph."""
        return self._bootstrap.dependency_graph

    @property
    def container(self) -> DependencyContainer:
        """Access the DI Container."""
        return self._bootstrap.container

    def register_service(self, service: KernelService) -> None:
        """Register a service into the kernel orchestrator."""
        self._bootstrap.register_service(service)

    def register_services(self, services: Sequence[KernelService]) -> None:
        """Register multiple services in batch."""
        self._bootstrap.register_services(services)

    async def boot(self) -> None:
        """Execute deterministic multi-stage OS Kernel startup sequence."""
        if self._is_running:
            logger.warning("KernelOrchestrator is already running.")
            return

        logger.info("Initiating OS Kernel Boot Sequence...")
        self._boot_id = f"boot-{uuid.uuid4().hex[:12]}"

        # 1. Prepare DI container
        self._bootstrap.prepare_container()

        # 2. Validate & Freeze dependency graph
        boot_order_ids, _ = self._bootstrap.validate_and_freeze()

        # 3. Resolve services in topological boot order
        boot_services: list[KernelService] = [self.registry.get(s_id) for s_id in boot_order_ids]

        # 4. Orchestrate service lifecycle startup with rollback protection
        try:
            await self.lifecycle.start_services_orchestrated(boot_services)
        except Exception as boot_err:
            self._is_running = False
            logger.error(f"Kernel Boot failed: {boot_err}")
            raise

        # 5. Start Runtime Scheduler & Background Worker pool
        self.scheduler.start()
        self.worker_manager.start()

        self._is_running = True
        logger.info(f"OS Kernel Boot completed successfully [Boot ID: {self._boot_id}].")

    async def shutdown(self) -> None:
        """Execute deterministic multi-stage OS Kernel graceful shutdown sequence."""
        if not self._is_running and self._boot_id is None:
            return

        logger.info(f"Initiating OS Kernel Graceful Shutdown [Boot ID: {self._boot_id}]...")

        # 1. Stop background schedulers and workers
        await self.scheduler.stop()
        await self.worker_manager.stop()

        # 2. Take pre-shutdown diagnostic snapshot
        try:
            await self.take_snapshot()
        except Exception as snap_err:
            logger.warning(f"Failed to create pre-shutdown snapshot: {snap_err}")

        # 3. Resolve shutdown order (reverse topological order)
        shutdown_order_ids = self.dependency_graph.get_shutdown_order()
        shutdown_services: list[KernelService] = []
        for s_id in shutdown_order_ids:
            if self.registry.has(s_id):
                shutdown_services.append(self.registry.get(s_id))

        # 4. Stop services in reverse topological order
        await self.lifecycle.stop_services_orchestrated(shutdown_services)

        self._is_running = False
        logger.info("OS Kernel Graceful Shutdown completed.")

    async def health(self) -> dict[str, Any]:
        """Aggregate health status across all registered kernel services."""
        services = self.registry.list_services()
        service_healths: dict[str, Any] = {}
        all_healthy = True

        for service in services:
            try:
                h = await service.health()
                service_healths[service.service_id] = h
                if not h.get("healthy", False):
                    all_healthy = False
            except Exception as err:
                all_healthy = False
                service_healths[service.service_id] = {
                    "healthy": False,
                    "error": str(err),
                }

        # Overall healthy if running, no failed services, and all service health probes return True
        overall_healthy = self._is_running and all_healthy and len(self.registry.list_failed()) == 0

        return {
            "kernel_version": NEXUSAI_VERSION,
            "boot_id": self._boot_id,
            "is_running": self._is_running,
            "healthy": overall_healthy,
            "total_services": len(services),
            "running_services": len(self.registry.list_running()),
            "failed_services": len(self.registry.list_failed()),
            "services": service_healths,
        }

    async def metrics(self) -> dict[str, Any]:
        """Aggregate telemetry metrics across all registered subsystem services (Memory, Brain, etc.)."""
        subsystem_metrics: dict[str, Any] = {}

        for service in self.registry.list_services():
            try:
                subsystem_metrics[service.service_id] = await service.metrics()
            except Exception as err:
                subsystem_metrics[service.service_id] = {"error": str(err)}

        return {
            "kernel_version": NEXUSAI_VERSION,
            "boot_id": self._boot_id,
            "is_running": self._is_running,
            "tasks": self.scheduler.list_tasks(),
            "workers": self.worker_manager.list_workers(),
            "subsystems": subsystem_metrics,
        }

    async def take_snapshot(self) -> KernelSnapshot:
        """Capture and record a current KernelSnapshot."""
        health_sum = await self.health()
        boot_id_str = self._boot_id or "unbooted"
        return await self.snapshot_manager.create_snapshot(
            boot_id=boot_id_str,
            registry=self.registry,
            scheduler=self.scheduler,
            worker_manager=self.worker_manager,
            health_summary=health_sum,
        )
