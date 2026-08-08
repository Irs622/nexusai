"""
Acceptance Tests for Phase 2.5 — Kernel Orchestration Engine.

Validates end-to-end failure resilience, topological boot ordering, state machine rollback,
and restart capabilities.
"""

import pytest

from nexusai.core.errors import KernelBootstrapError
from nexusai.kernel.contracts import KernelService, ServiceDescriptor, ServiceLifecycleState
from nexusai.kernel.orchestrator import KernelOrchestrator


class AcceptanceTestSubsystem(KernelService):
    def __init__(self, descriptor: ServiceDescriptor, fail_on_start: bool = False):
        super().__init__(descriptor)
        self.fail_on_start = fail_on_start
        self.init_count = 0
        self.start_count = 0
        self.stop_count = 0

    async def initialize(self) -> None:
        self.init_count += 1
        self.set_state(ServiceLifecycleState.INITIALIZED)

    async def start(self) -> None:
        self.start_count += 1
        if self.fail_on_start:
            raise RuntimeError(f"Simulated startup failure in '{self.service_id}'")
        self.set_state(ServiceLifecycleState.RUNNING)

    async def stop(self) -> None:
        self.stop_count += 1
        self.set_state(ServiceLifecycleState.STOPPED)


@pytest.mark.asyncio
async def test_acceptance_boot_failure_recovery():
    """Acceptance Test 1: Boot Failure Recovery

    Sequence:
    Service A starts
    ↓
    Service B starts
    ↓
    Service C fails on start
    ↓
    Automated Rollback (ROLLING_BACK)
    ↓
    Service A stopped & Service B stopped
    ↓
    Kernel health is False
    """
    orchestrator = KernelOrchestrator()

    srv_a = AcceptanceTestSubsystem(
        ServiceDescriptor(id="service_a", name="Service A", version="1.0.0")
    )
    srv_b = AcceptanceTestSubsystem(
        ServiceDescriptor(
            id="service_b", name="Service B", version="1.0.0", dependencies=("service_a",)
        )
    )
    srv_c = AcceptanceTestSubsystem(
        ServiceDescriptor(
            id="service_c", name="Service C", version="1.0.0", dependencies=("service_b",)
        ),
        fail_on_start=True,
    )

    orchestrator.register_services([srv_a, srv_b, srv_c])

    # Boot should fail on Service C
    with pytest.raises(KernelBootstrapError) as exc_info:
        await orchestrator.boot()

    assert "service_c" in str(exc_info.value)
    assert orchestrator.is_running is False

    # Check state machine rollbacks
    assert srv_a.state == ServiceLifecycleState.STOPPED
    assert srv_a.stop_count == 1

    assert srv_b.state == ServiceLifecycleState.STOPPED
    assert srv_b.stop_count == 1

    assert srv_c.state == ServiceLifecycleState.FAILED

    # Kernel health check must report healthy == False
    health = await orchestrator.health()
    assert health["healthy"] is False
    assert health["failed_services"] == 1


@pytest.mark.asyncio
async def test_acceptance_restart_after_failure():
    """Acceptance Test 2: Restart After Failure

    Sequence:
    boot (fails on Service C)
    ↓
    rollback executed
    ↓
    fix Service C (fail_on_start = False)
    ↓
    re-boot kernel
    ↓
    all services reach RUNNING and Kernel health is True
    """
    orchestrator = KernelOrchestrator()

    srv_a = AcceptanceTestSubsystem(
        ServiceDescriptor(id="service_a", name="Service A", version="1.0.0")
    )
    srv_b = AcceptanceTestSubsystem(
        ServiceDescriptor(
            id="service_b", name="Service B", version="1.0.0", dependencies=("service_a",)
        )
    )
    srv_c = AcceptanceTestSubsystem(
        ServiceDescriptor(
            id="service_c", name="Service C", version="1.0.0", dependencies=("service_b",)
        ),
        fail_on_start=True,
    )

    orchestrator.register_services([srv_a, srv_b, srv_c])

    # First boot attempt fails
    with pytest.raises(KernelBootstrapError):
        await orchestrator.boot()

    assert orchestrator.is_running is False
    assert srv_c.state == ServiceLifecycleState.FAILED

    # Fix Service C
    srv_c.fail_on_start = False

    # Re-boot kernel
    await orchestrator.boot()

    assert orchestrator.is_running is True
    assert srv_a.state == ServiceLifecycleState.RUNNING
    assert srv_b.state == ServiceLifecycleState.RUNNING
    assert srv_c.state == ServiceLifecycleState.RUNNING

    health = await orchestrator.health()
    assert health["healthy"] is True
    assert health["running_services"] == 3
    assert health["failed_services"] == 0

    # Clean shutdown
    await orchestrator.shutdown()
    assert orchestrator.is_running is False
