"""WorldState domain model representing current workspace, environment, tools, and system resources."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SystemResourceUsage:
    """Snapshot of current system resource usage."""

    cpu_percent: float = 5.0
    ram_mb: float = 256.0
    active_workers: int = 1


@dataclass(frozen=True)
class WorldState:
    """Domain model representing the current external world state.

    Attributes:
        workspace_path: Absolute workspace root path string.
        environment_vars: Key-value map of relevant environment variables.
        connected_mcp_servers: List of active connected MCP server identifiers.
        available_capabilities: List of currently discovered capability names.
        file_system_snapshot: Key-value map of file paths to modified timestamps or state hashes.
        resources: SystemResourceUsage snapshot.
        timestamp: Epoch timestamp float when captured.
    """

    workspace_path: str = "/workspace"
    environment_vars: dict[str, str] = field(default_factory=dict)
    connected_mcp_servers: tuple[str, ...] = ()
    available_capabilities: tuple[str, ...] = ()
    file_system_snapshot: dict[str, str] = field(default_factory=dict)
    resources: SystemResourceUsage = field(default_factory=SystemResourceUsage)
    timestamp: float = field(default_factory=time.time)
