"""
Unit tests for KernelOrchestrator facade.
"""

import pytest

from nexusai.kernel.contracts import KernelService, ServiceDescriptor, ServiceLifecycleState
from nexusai.kernel.orchestrator import KernelOrchestrator


class MockKernelSubsystem(KernelService):
    def __init__(self, descriptor: ServiceDescriptor):
        super().__init__(descriptor)
        self.metrics_called = False

    async def initialize(self) -> None:
        self.set_state(ServiceLifecycleState.INITIALIZED)

    async def start(self) -> None:
        self.set_state(ServiceLifecycleState.RUNNING)

    async def stop(self) -> None:
        self.set_state(ServiceLifecycleState.STOPPED)

    async def metrics(self) -> dict[str, str]:
        self.metrics_called = True
        return {"subsystem": self.service_id, "status": "ok"}


@pytest.mark.asyncio
async def test_kernel_orchestrator_boot_shutdown_and_metrics():
    orchestrator = KernelOrchestrator()

    # DB -> Memory -> Brain
    s_db = MockKernelSubsystem(ServiceDescriptor(id="db", name="DB", version="1.0.0"))
    s_mem = MockKernelSubsystem(ServiceDescriptor(id="memory", name="Memory", version="1.0.0", dependencies=("db",)))
    s_brain = MockKernelSubsystem(ServiceDescriptor(id="brain", name="Brain", version="1.0.0", dependencies=("memory",)))

    orchestrator.register_services([s_brain, s_db, s_mem])

    assert orchestrator.is_running is False
    await orchestrator.boot()

    assert orchestrator.is_running is True
    assert orchestrator.boot_id is not None
    assert s_db.state == ServiceLifecycleState.RUNNING
    assert s_mem.state == ServiceLifecycleState.RUNNING
    assert s_brain.state == ServiceLifecycleState.RUNNING

    # Health check
    h = await orchestrator.health()
    assert h["healthy"] is True
    assert h["total_services"] == 3
    assert h["running_services"] == 3

    # Metrics aggregation check
    m = await orchestrator.metrics()
    assert "subsystems" in m
    assert m["subsystems"]["db"]["status"] == "ok"
    assert s_db.metrics_called is True

    # Take snapshot check
    snap = await orchestrator.take_snapshot()
    assert snap.boot_id == orchestrator.boot_id
    assert "db" in snap.services

    # Graceful shutdown
    await orchestrator.shutdown()
    assert orchestrator.is_running is False
    assert s_db.state == ServiceLifecycleState.STOPPED
    assert s_mem.state == ServiceLifecycleState.STOPPED
    assert s_brain.state == ServiceLifecycleState.STOPPED
