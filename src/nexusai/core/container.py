"""
Simple Dependency Injection Container for NexusAI services.
"""

from typing import Any, TypeVar, Callable

T = TypeVar("T")


class DependencyContainer:
    """Lightweight thread-safe Dependency Injection Container."""

    def __init__(self) -> None:
        self._services: dict[type[Any], Any] = {}
        self._factories: dict[type[Any], Callable[['DependencyContainer'], Any]] = {}

    def register_singleton(self, service_type: type[T], instance: T) -> None:
        """Register an existing singleton instance."""
        self._services[service_type] = instance

    def register_factory(self, service_type: type[T], factory: Callable[['DependencyContainer'], T]) -> None:
        """Register a factory function for a service type."""
        self._factories[service_type] = factory

    def resolve(self, service_type: type[T]) -> T:
        """Resolve a service by type."""
        if service_type in self._services:
            return self._services[service_type]  # type: ignore[no-any-return]

        if service_type in self._factories:
            instance = self._factories[service_type](self)
            self._services[service_type] = instance
            return instance  # type: ignore[no-any-return]

        raise KeyError(f"Service of type '{service_type.__name__}' is not registered in container.")

    def clear(self) -> None:
        """Clear all registered services."""
        self._services.clear()
        self._factories.clear()
