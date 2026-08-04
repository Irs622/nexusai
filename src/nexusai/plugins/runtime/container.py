"""
IoC ServiceContainer for dependency injection of kernel services.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class ServiceLifetime(str, Enum):
    """Lifetime of registered container service."""

    SINGLETON = "SINGLETON"
    TRANSIENT = "TRANSIENT"


class ServiceContainer:
    """Inversion of Control (IoC) Dependency Injection container."""

    def __init__(self) -> None:
        self._services: dict[type[Any], tuple[ServiceLifetime, Callable[[], Any], Any]] = {}

    def register_singleton(self, service_type: type[T], instance: T) -> None:
        """Register a pre-instantiated singleton service."""
        self._services[service_type] = (ServiceLifetime.SINGLETON, lambda: instance, instance)

    def register_factory(self, service_type: type[T], factory: Callable[[], T], lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT) -> None:
        """Register a service factory with specified lifetime."""
        self._services[service_type] = (lifetime, factory, None)

    def resolve(self, service_type: type[T]) -> T:
        """Resolve service instance by type.

        Raises:
            KeyError: If service_type is not registered in container.
        """
        if service_type not in self._services:
            raise KeyError(f"Service '{service_type.__name__}' is not registered in ServiceContainer")

        lifetime, factory, instance = self._services[service_type]
        if lifetime == ServiceLifetime.SINGLETON:
            if instance is None:
                instance = factory()
                self._services[service_type] = (lifetime, factory, instance)
            return instance  # type: ignore[no-any-return]
        else:
            return factory()  # type: ignore[no-any-return]

    def has_service(self, service_type: type[Any]) -> bool:
        """Return True if service_type is registered."""
        return service_type in self._services
