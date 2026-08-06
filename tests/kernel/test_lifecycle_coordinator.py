"""
Unit tests for LifecycleCoordinator.
"""

import pytest

from nexusai.core.errors import KernelBootstrapError, LifecycleStateError
from nexusai.kernel.contracts import KernelService, ServiceDescriptor, ServiceLifecycleState
from nexusai.kernel.lifecycle import LifecycleCoordinator


class DummyStatefulService(KernelService):
    def __init__(self, descriptor: ServiceDescriptor, fail_on_start: bool = False):
        super().__init__(descriptor)
        self.fail_on_start = fail_on_start
        self.initialized = False
        self.started = False
        self.stopped = False

    async def initialize(self) -> None:
        self.initialized = True

    async def start(self) -> None:
        if self.fail_on_start:
            raise RuntimeError(f"Simulated start failure in {self.service_id}")
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


@pytest.mark.asyncio
async def test_lifecycle_coordinator_normal_flow():
    coordinator = LifecycleCoordinator()
    service = DummyStatefulService(ServiceDescriptor(id="s1", name="S1", version="1.0.0"))

    await coordinator.initialize_service(service)
    assert service.state == ServiceLifecycleState.INITIALIZED
    assert service.initialized is True

    await coordinator.start_service(service)
    assert service.state == ServiceLifecycleState.RUNNING
    assert service.started is True

    await coordinator.stop_service(service)
    assert service.state == ServiceLifecycleState.STOPPED
    assert service.stopped is True


@pytest.mark.asyncio
async def test_lifecycle_coordinator_orchestrated_rollback():
    coordinator = LifecycleCoordinator()

    s1 = DummyStatefulService(ServiceDescriptor(id="s1", name="S1", version="1.0.0"))
    s2 = DummyStatefulService(ServiceDescriptor(id="s2", name="S2", version="1.0.0"), fail_on_start=True)
    s3 = DummyStatefulService(ServiceDescriptor(id="s3", name="S3", version="1.0.0"))

    boot_list = [s1, s2, s3]

    with pytest.raises(KernelBootstrapError):
        await coordinator.start_services_orchestrated(boot_list)

    # s1 was started, so it should be rolled back to STOPPED
    assert s1.stopped is True
    assert s1.state == ServiceLifecycleState.STOPPED

    # s2 failed on start, so its state should be FAILED
    assert s2.state == ServiceLifecycleState.FAILED
