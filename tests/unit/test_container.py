"""
Unit tests for Dependency Injection Container.
"""

import pytest
from nexusai.core.container import DependencyContainer


class DummyService:
    def __init__(self, value: str = "default") -> None:
        self.value = value


def test_container_singleton_registration(container: DependencyContainer) -> None:
    instance = DummyService("test")
    container.register_singleton(DummyService, instance)

    resolved = container.resolve(DummyService)
    assert resolved is instance
    assert resolved.value == "test"


def test_container_factory_registration(container: DependencyContainer) -> None:
    container.register_factory(DummyService, lambda c: DummyService("factory"))

    resolved = container.resolve(DummyService)
    assert resolved.value == "factory"


def test_container_unregistered_service(container: DependencyContainer) -> None:
    with pytest.raises(KeyError):
        container.resolve(DummyService)
