"""
Service Registry for NexusAI OS Kernel.
"""

from __future__ import annotations

import threading
from typing import Any, TypeVar

from nexusai.core.errors import ServiceRegistrationError
from nexusai.kernel.contracts import KernelService, ServiceLifecycleState
from nexusai.logging.logger import logger

T = TypeVar("T")


class ServiceRegistry:
    """Thread-safe registry for KernelService lookup, filtering, and lifecycle monitoring."""

    def __init__(self) -> None:
        self._services: dict[str, KernelService] = {}
        self._lock = threading.RLock()

    def register(self, service: KernelService) -> None:
        """Register a KernelService instance into the registry.

        Raises:
            ServiceRegistrationError: If service is invalid or ID already registered.
        """
        if not isinstance(service, KernelService):
            raise ServiceRegistrationError(
                f"Object '{service}' must inherit from KernelService"
            )

        service_id = service.service_id
        if not service_id:
            raise ServiceRegistrationError("Service descriptor ID cannot be empty.")

        with self._lock:
            if service_id in self._services:
                raise ServiceRegistrationError(
                    f"Service with ID '{service_id}' is already registered in ServiceRegistry."
                )

            self._services[service_id] = service
            logger.info(
                f"Registered KernelService '{service.descriptor.name}' [ID: {service_id}, Version: {service.descriptor.version}]"
            )

    def unregister(self, service_id: str) -> KernelService:
        """Unregister and return a service by ID.

        Raises:
            ServiceRegistrationError: If service is not registered.
        """
        with self._lock:
            if service_id not in self._services:
                raise ServiceRegistrationError(
                    f"Service with ID '{service_id}' is not registered."
                )
            service = self._services.pop(service_id)
            logger.info(f"Unregistered KernelService [ID: {service_id}]")
            return service

    def get(self, service_id: str) -> KernelService:
        """Retrieve a registered service by ID.

        Raises:
            ServiceRegistrationError: If service is not registered.
        """
        with self._lock:
            if service_id not in self._services:
                raise ServiceRegistrationError(
                    f"Service with ID '{service_id}' is not registered."
                )
            return self._services[service_id]

    def has(self, service_id: str) -> bool:
        """Check if a service ID is currently registered."""
        with self._lock:
            return service_id in self._services

    def get_by_interface(self, interface_cls: type[T]) -> list[T]:
        """Retrieve all registered services that implement or inherit from interface_cls."""
        with self._lock:
            matching: list[T] = []
            for service in self._services.values():
                if isinstance(service, interface_cls):
                    matching.append(service)  # type: ignore[arg-type]
            return matching

    def get_by_tag(self, tag: str) -> list[KernelService]:
        """Retrieve all registered services matching a given tag."""
        with self._lock:
            return [
                service
                for service in self._services.values()
                if tag in service.descriptor.tags
            ]

    def list_services(self) -> list[KernelService]:
        """Return a snapshot list of all registered services."""
        with self._lock:
            return list(self._services.values())

    def list_running(self) -> list[KernelService]:
        """Return all services in RUNNING lifecycle state."""
        with self._lock:
            return [
                service
                for service in self._services.values()
                if service.state == ServiceLifecycleState.RUNNING
            ]

    def list_failed(self) -> list[KernelService]:
        """Return all services in FAILED lifecycle state."""
        with self._lock:
            return [
                service
                for service in self._services.values()
                if service.state == ServiceLifecycleState.FAILED
            ]

    def clear(self) -> None:
        """Clear all registered services."""
        with self._lock:
            self._services.clear()
            logger.info("ServiceRegistry cleared.")
