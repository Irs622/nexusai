"""
Unit tests for SnapshotManager.
"""

import pytest

from nexusai.kernel.contracts import KernelService, ServiceDescriptor, ServiceLifecycleState
from nexusai.kernel.registry import ServiceRegistry
from nexusai.kernel.scheduler import RuntimeScheduler
from nexusai.kernel.snapshot import SnapshotManager
from nexusai.kernel.worker import BackgroundWorkerManager


class DummySnapshotService(KernelService):
    async def initialize(self) -> None:
        self.set_state(ServiceLifecycleState.INITIALIZED)

    async def start(self) -> None:
        self.set_state(ServiceLifecycleState.RUNNING)

    async def stop(self) -> None:
        self.set_state(ServiceLifecycleState.STOPPED)


@pytest.mark.asyncio
async def test_snapshot_manager_create_export_load(tmp_path):
    manager = SnapshotManager(kernel_version="2.5.0")
    registry = ServiceRegistry()
    scheduler = RuntimeScheduler()
    worker_mgr = BackgroundWorkerManager()

    srv = DummySnapshotService(ServiceDescriptor(id="s1", name="S1", version="1.0.0"))
    await srv.initialize()
    await srv.start()
    registry.register(srv)

    health_sum = {"healthy": True, "services_count": 1}

    snapshot = await manager.create_snapshot(
        boot_id="boot-12345",
        registry=registry,
        scheduler=scheduler,
        worker_manager=worker_mgr,
        health_summary=health_sum,
    )

    assert snapshot.boot_id == "boot-12345"
    assert snapshot.kernel_version == "2.5.0"
    assert "s1" in snapshot.services
    assert snapshot.services["s1"]["state"] == "RUNNING"
    assert snapshot.health["healthy"] is True

    json_str = manager.export_json(snapshot)
    loaded = SnapshotManager.load_from_json(json_str)

    assert loaded.boot_id == "boot-12345"
    assert loaded.services["s1"]["state"] == "RUNNING"

    file_path = tmp_path / "snapshot.json"
    manager.save_to_file(snapshot, file_path)
    assert file_path.exists()
