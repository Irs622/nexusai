"""Domain models for gRPC container sandbox execution and isolation policy limits."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ResourceLimits:
    """Resource bounds for containerized tool execution."""

    cpu_cores: float = 1.0
    memory_limit_mb: int = 512
    timeout_seconds: float = 30.0
    max_pids: int = 64


@dataclass(frozen=True)
class IsolationPolicy:
    """Security isolation flags for container sandbox."""

    read_only_rootfs: bool = True
    allow_network_egress: bool = False
    allowed_host_paths: Sequence[str] = field(default_factory=list)
    allowed_capabilities: Sequence[str] = field(default_factory=list)
    drop_all_capabilities: bool = True
    run_as_non_root: bool = True


@dataclass(frozen=True)
class SandboxSpec:
    """Complete specification payload for executing a tool in a isolated sandbox."""

    tool_id: str
    execution_id: str
    session_id: str
    fencing_token: int
    arguments: Mapping[str, Any]
    limits: ResourceLimits = field(default_factory=ResourceLimits)
    policy: IsolationPolicy = field(default_factory=IsolationPolicy)
    ephemeral_env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SandboxResult:
    """Result payload returned by sandbox execution gateway."""

    execution_id: str
    success: bool
    output: Any
    exit_code: int = 0
    error_message: str = ""
    duration_ms: float = 0.0
    memory_peak_mb: float = 0.0
