"""
Unit tests for IoC ServiceContainer.
"""

import pytest
from nexusai.plugins.runtime.container import ServiceContainer, ServiceLifetime


class MockDatabaseService:
    def __init__(self) -> None:
        self.connected = True


def test_service_container_singleton_registration():
    container = ServiceContainer()
    db_service = MockDatabaseService()

    container.register_singleton(MockDatabaseService, db_service)
    assert container.has_service(MockDatabaseService) is True

    resolved = container.resolve(MockDatabaseService)
    assert resolved is db_service


def test_service_container_transient_factory():
    container = ServiceContainer()
    counter = 0

    def factory() -> MockDatabaseService:
        nonlocal counter
        counter += 1
        return MockDatabaseService()

    container.register_factory(MockDatabaseService, factory, lifetime=ServiceLifetime.TRANSIENT)

    instance1 = container.resolve(MockDatabaseService)
    instance2 = container.resolve(MockDatabaseService)

    assert instance1 is not instance2
    assert counter == 2


def test_service_container_unregistered_throws():
    container = ServiceContainer()
    with pytest.raises(KeyError):
        container.resolve(MockDatabaseService)
