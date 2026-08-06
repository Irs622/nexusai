"""
Lifecycle Coordinator for managing KernelService transitions and failure rollbacks.
"""

from __future__ import annotations

from typing import Sequence

from nexusai.core.errors import KernelBootstrapError, LifecycleStateError
from nexusai.kernel.contracts import KernelService, ServiceLifecycleState
from nexusai.logging.logger import logger


class LifecycleCoordinator:
    """Coordinates lifecycle transitions across single or multiple kernel services with rollback protection."""

    async def initialize_service(self, service: KernelService) -> None:
        """Initialize a single service."""
        if service.state not in (ServiceLifecycleState.UNINITIALIZED, ServiceLifecycleState.STOPPED):
            raise LifecycleStateError(
                f"Cannot initialize service '{service.service_id}' from state {service.state.value}."
            )
        try:
            logger.info(f"Initializing service '{service.service_id}'...")
            await service.initialize()
            service.set_state(ServiceLifecycleState.INITIALIZED)
        except Exception as err:
            service.set_state(ServiceLifecycleState.FAILED)
            logger.error(f"Initialization failed for service '{service.service_id}': {err}")
            raise LifecycleStateError(f"Failed to initialize service '{service.service_id}': {err}") from err

    async def start_service(self, service: KernelService) -> None:
        """Start a single service."""
        if service.state != ServiceLifecycleState.INITIALIZED:
            raise LifecycleStateError(
                f"Cannot start service '{service.service_id}' from state {service.state.value}. Must be INITIALIZED."
            )
        try:
            logger.info(f"Starting service '{service.service_id}'...")
            service.set_state(ServiceLifecycleState.STARTING)
            await service.start()
            service.set_state(ServiceLifecycleState.RUNNING)
        except Exception as err:
            service.set_state(ServiceLifecycleState.FAILED)
            logger.error(f"Startup failed for service '{service.service_id}': {err}")
            raise LifecycleStateError(f"Failed to start service '{service.service_id}': {err}") from err

    async def stop_service(self, service: KernelService) -> None:
        """Stop a single service."""
        if service.state in (ServiceLifecycleState.STOPPED, ServiceLifecycleState.UNINITIALIZED):
            return

        try:
            logger.info(f"Stopping service '{service.service_id}'...")
            service.set_state(ServiceLifecycleState.STOPPING)
            await service.stop()
            service.set_state(ServiceLifecycleState.STOPPED)
        except Exception as err:
            service.set_state(ServiceLifecycleState.FAILED)
            logger.error(f"Stop failed for service '{service.service_id}': {err}")
            raise LifecycleStateError(f"Failed to stop service '{service.service_id}': {err}") from err

    async def shutdown_service(self, service: KernelService) -> None:
        """Perform full shutdown and cleanup on a single service."""
        try:
            logger.info(f"Shutting down service '{service.service_id}'...")
            service.set_state(ServiceLifecycleState.STOPPING)
            await service.shutdown()
            service.set_state(ServiceLifecycleState.STOPPED)
        except Exception as err:
            service.set_state(ServiceLifecycleState.FAILED)
            logger.error(f"Shutdown failed for service '{service.service_id}': {err}")
            raise LifecycleStateError(f"Failed to shutdown service '{service.service_id}': {err}") from err

    async def start_services_orchestrated(self, boot_services: Sequence[KernelService]) -> None:
        """Initialize and start a list of services in topological boot order.

        If any service fails during initialize or start:
        1. Set failed service to FAILED.
        2. Set state to ROLLING_BACK.
        3. Stop already-started services in reverse boot order.
        4. Transition stopped services to STOPPED.
        5. Raise KernelBootstrapError.
        """
        started_services: list[KernelService] = []

        # 1. Initialize all services
        for service in boot_services:
            try:
                await self.initialize_service(service)
            except Exception as err:
                await self._rollback_started_services(started_services, failed_service=service)
                raise KernelBootstrapError(
                    f"Kernel bootstrap failed during initialization of '{service.service_id}': {err}"
                ) from err

        # 2. Start all services
        for service in boot_services:
            try:
                await self.start_service(service)
                started_services.append(service)
            except Exception as err:
                await self._rollback_started_services(started_services, failed_service=service)
                raise KernelBootstrapError(
                    f"Kernel bootstrap failed during startup of '{service.service_id}': {err}"
                ) from err

    async def stop_services_orchestrated(self, shutdown_services: Sequence[KernelService]) -> None:
        """Stop a list of services in reverse topological order."""
        for service in shutdown_services:
            try:
                await self.stop_service(service)
            except Exception as err:
                logger.warning(f"Non-fatal error stopping service '{service.service_id}': {err}")

    async def _rollback_started_services(
        self,
        started_services: list[KernelService],
        failed_service: KernelService,
    ) -> None:
        """Perform automated rollback of already started services upon boot failure."""
        logger.warning(f"Initiating lifecycle ROLLING_BACK due to failure in '{failed_service.service_id}'...")

        failed_service.set_state(ServiceLifecycleState.FAILED)

        # Rollback started services in reverse order
        for service in reversed(started_services):
            try:
                service.set_state(ServiceLifecycleState.ROLLING_BACK)
                await service.stop()
                service.set_state(ServiceLifecycleState.STOPPED)
            except Exception as rollback_err:
                logger.error(f"Error rolling back service '{service.service_id}': {rollback_err}")
                service.set_state(ServiceLifecycleState.FAILED)
