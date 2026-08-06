"""
Unit tests for ServiceRegistry.
"""

from typing import Any
import pytest

from nexusai.core.errors import ServiceRegistrationError
from nexusai.kernel.contracts import KernelService, ServiceDescriptor, ServiceLifecycleState
from nexusai.kernel.registry import ServiceRegistry


class MockSubsystemService(KernelService):
    """Mock KernelService for testing."""

    async def initialize(self) -> None:
        self.set_state(ServiceLifecycleState.INITIALIZED)

    async def start(self) -> None:
        self.set_state(ServiceLifecycleState.RUNNING)

    async def stop(self) -> None:
        self.set_state(ServiceLifecycleState.STOPPED)


class CustomInterface(KernelService):
    """Marker interface for type lookup tests."""

    pass


class InterfaceImplementorService(CustomInterface):
    """Service implementing CustomInterface."""

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


def test_service_registry_registration_and_lookup():
    registry = ServiceRegistry()
    desc = ServiceDescriptor(id="service.a", name="Service A", version="1.0.0", tags=("core", "test"))
    srv = MockSubsystemService(desc)

    registry.register(srv)
    assert registry.has("service.a") is True
    assert registry.get("service.a") is srv
    assert len(registry.list_services()) == 1

    # Duplicate registration raises error
    with pytest.raises(ServiceRegistrationError):
        registry.register(srv)


def test_service_registry_lookup_by_interface_and_tag():
    registry = ServiceRegistry()
    srv_a = MockSubsystemService(ServiceDescriptor(id="a", name="A", version="1.0.0", tags=("tag1",)))
    srv_b = InterfaceImplementorService(ServiceDescriptor(id="b", name="B", version="1.0.0", tags=("tag1", "tag2")))

    registry.register(srv_a)
    registry.register(srv_b)

    by_interface = registry.get_by_interface(CustomInterface)
    assert len(by_interface) == 1
    assert by_interface[0] is srv_b

    by_tag1 = registry.get_by_tag("tag1")
    assert len(by_tag1) == 2

    by_tag2 = registry.get_by_tag("tag2")
    assert len(by_tag2) == 1
    assert by_tag2[0] is srv_b


def test_service_registry_filters():
    registry = ServiceRegistry()
    srv1 = MockSubsystemService(ServiceDescriptor(id="s1", name="S1", version="1.0.0"))
    srv2 = MockSubsystemService(ServiceDescriptor(id="s2", name="S2", version="1.0.0"))

    registry.register(srv1)
    registry.register(srv2)

    assert len(registry.list_running()) == 0
    assert len(registry.list_failed()) == 0

    srv1.set_state(ServiceLifecycleState.RUNNING)
    srv2.set_state(ServiceLifecycleState.FAILED)

    assert len(registry.list_running()) == 1
    assert registry.list_running()[0] is srv1

    assert len(registry.list_failed()) == 1
    assert registry.list_failed()[0] is srv2


def test_service_registry_unregister_and_clear():
    registry = ServiceRegistry()
    srv = MockSubsystemService(ServiceDescriptor(id="s1", name="S1", version="1.0.0"))
    registry.register(srv)

    removed = registry.unregister("s1")
    assert removed is srv
    assert registry.has("s1") is False

    with pytest.raises(ServiceRegistrationError):
        registry.get("s1")

    registry.register(srv)
    registry.clear()
    assert len(registry.list_services()) == 0
