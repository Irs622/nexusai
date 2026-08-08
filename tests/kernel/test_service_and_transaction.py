"""
Unit tests for KernelService, ServiceDescriptor, AsyncTransaction, and probes.
"""

import pytest

from nexusai.kernel.service import KernelService, ServiceDescriptor, ServiceLifecycleState
from nexusai.kernel.transaction import AsyncTransaction


class DummyService(KernelService):
    """Dummy KernelService implementation for testing."""

    async def initialize(self) -> None:
        self._state = ServiceLifecycleState.INITIALIZED

    async def start(self) -> None:
        self._state = ServiceLifecycleState.RUNNING

    async def stop(self) -> None:
        self._state = ServiceLifecycleState.STOPPED


class DummyTransaction(AsyncTransaction):
    """Dummy AsyncTransaction implementation for testing."""

    def __init__(self) -> None:
        self.begun = False
        self.committed = False
        self.rolled_back = False

    async def begin(self) -> None:
        self.begun = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


@pytest.mark.asyncio
async def test_kernel_service_lifecycle_and_probes():
    descriptor = ServiceDescriptor(
        id="kernel.dummy",
        name="Dummy Service",
        version="1.0.0",
    )
    service = DummyService(descriptor)

    assert service.service_id == "kernel.dummy"
    assert service.state == ServiceLifecycleState.UNINITIALIZED
    assert await service.readiness() is False
    assert await service.liveness() is True

    await service.initialize()
    assert service.state == ServiceLifecycleState.INITIALIZED

    await service.start()
    assert service.state == ServiceLifecycleState.RUNNING
    assert await service.readiness() is True
    assert await service.liveness() is True

    health = await service.health()
    assert health["healthy"] is True

    await service.stop()
    assert service.state == ServiceLifecycleState.STOPPED
    assert await service.readiness() is False


@pytest.mark.asyncio
async def test_async_transaction_context_manager_commit():
    tx = DummyTransaction()
    async with tx:
        pass

    assert tx.begun is True
    assert tx.committed is True
    assert tx.rolled_back is False


@pytest.mark.asyncio
async def test_async_transaction_context_manager_rollback():
    tx = DummyTransaction()
    with pytest.raises(ValueError):
        async with tx:
            raise ValueError("Test error")

    assert tx.begun is True
    assert tx.committed is False
    assert tx.rolled_back is True
