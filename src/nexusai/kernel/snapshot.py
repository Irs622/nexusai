"""
Snapshot Manager for NexusAI OS Kernel state diagnostics, recovery, and audit trails.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from nexusai import __version__ as NEXUSAI_VERSION
from nexusai.kernel.registry import ServiceRegistry
from nexusai.kernel.scheduler import RuntimeScheduler
from nexusai.kernel.worker import BackgroundWorkerManager
from nexusai.logging.logger import logger


@dataclass(frozen=True)
class KernelSnapshot:
    """Immutable snapshot container representing full system state at a specific point in time."""

    timestamp: str
    kernel_version: str
    boot_id: str
    services: dict[str, dict[str, Any]]
    workers: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    health: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert snapshot object to dictionary."""
        return asdict(self)

    def to_json(self, indent: int | None = 2) -> str:
        """Serialize snapshot to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


class SnapshotManager:
    """Manages creation, serialization, persistence, and loading of KernelSnapshots."""

    def __init__(self, kernel_version: str = NEXUSAI_VERSION) -> None:
        self.kernel_version = kernel_version
        self._history: list[KernelSnapshot] = []

    async def create_snapshot(
        self,
        boot_id: str,
        registry: ServiceRegistry,
        scheduler: RuntimeScheduler,
        worker_manager: BackgroundWorkerManager,
        health_summary: dict[str, Any],
    ) -> KernelSnapshot:
        """Capture an immutable KernelSnapshot of the current runtime state."""
        timestamp = datetime.now(timezone.utc).isoformat()

        # Capture services state, descriptor metadata, and metrics
        services_dict: dict[str, dict[str, Any]] = {}
        for service in registry.list_services():
            s_id = service.service_id
            metrics = {}
            try:
                metrics = await service.metrics()
            except Exception as err:
                logger.warning(f"Failed to collect metrics from service '{s_id}': {err}")

            services_dict[s_id] = {
                "name": service.descriptor.name,
                "version": service.descriptor.version,
                "state": service.state.value,
                "dependencies": service.descriptor.dependencies,
                "metrics": metrics,
            }

        # Capture worker pool & task scheduler states
        workers_list = worker_manager.list_workers()
        tasks_list = scheduler.list_tasks()

        snapshot = KernelSnapshot(
            timestamp=timestamp,
            kernel_version=self.kernel_version,
            boot_id=boot_id,
            services=services_dict,
            workers=workers_list,
            tasks=tasks_list,
            health=health_summary,
        )

        self._history.append(snapshot)
        logger.info(f"Created KernelSnapshot [Boot ID: {boot_id}, Timestamp: {timestamp}]")
        return snapshot

    def export_json(self, snapshot: KernelSnapshot) -> str:
        """Export snapshot to JSON string."""
        return snapshot.to_json()

    def save_to_file(self, snapshot: KernelSnapshot, file_path: str | Path) -> None:
        """Save a KernelSnapshot to a JSON file on disk."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(snapshot.to_json(), encoding="utf-8")
        logger.info(f"Saved KernelSnapshot to '{path}'")

    @staticmethod
    def load_from_json(json_str: str) -> KernelSnapshot:
        """Parse JSON string into KernelSnapshot dataclass instance."""
        data = json.loads(json_str)
        return KernelSnapshot(
            timestamp=data["timestamp"],
            kernel_version=data["kernel_version"],
            boot_id=data["boot_id"],
            services=data.get("services", {}),
            workers=data.get("workers", []),
            tasks=data.get("tasks", []),
            health=data.get("health", {}),
        )

    def get_history(self) -> list[KernelSnapshot]:
        """Return list of snapshots created during this session."""
        return list(self._history)
