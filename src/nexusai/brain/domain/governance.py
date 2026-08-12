"""Domain models for Capability Governance, Resource Budgets, Reservations, and Admission Control Decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Mapping


class ToolCapability(str, Enum):
    """Explicit tool capabilities taxonomy for admission governance."""

    FILE_READ = "file.read"
    FILE_WRITE = "file.write"
    FILE_DELETE = "file.delete"
    PROCESS_EXEC = "process.exec"
    NETWORK_ACCESS = "network.access"
    SYSTEM_CONTROL = "system.control"
    SECRET_ACCESS = "secret.access"


class GovernanceDenialReason(str, Enum):
    """Explicit taxonomy for governance denial reasons."""

    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
    CAPABILITY_MISSING = "CAPABILITY_MISSING"
    GRANT_EXPIRED = "GRANT_EXPIRED"
    GRANT_EXECUTION_MISMATCH = "GRANT_EXECUTION_MISMATCH"
    RESOURCE_QUOTA_EXCEEDED = "RESOURCE_QUOTA_EXCEEDED"
    MALFORMED_RESOURCE_REQUEST = "MALFORMED_RESOURCE_REQUEST"
    POLICY_VIOLATION = "POLICY_VIOLATION"


@dataclass(frozen=True)
class ResourceBudget:
    """Immutable execution resource budget limits."""

    max_concurrent_tasks: int = 4
    max_cpu_seconds: float = 300.0
    max_memory_bytes: int = 512 * 1024 * 1024  # 512MB
    max_subprocesses: int = 10
    max_network_requests: int = 50
    max_tool_invocations: int = 100


@dataclass(frozen=True)
class ResourceRequest:
    """Requested resources for a single node execution."""

    subprocesses: int = 0
    network_requests: int = 0
    memory_bytes: int = 0
    tool_invocations: int = 1


@dataclass(frozen=True)
class ResourceReservation:
    """Reserved resources active before execution."""

    reservation_id: str
    execution_id: str
    node_id: str
    subprocesses: int
    network_requests: int
    memory_bytes: int
    tool_invocations: int
    reserved_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ResourceUsage:
    """Resources actually consumed during execution."""

    subprocesses_used: int = 0
    network_requests_used: int = 0
    memory_bytes_used: int = 0
    tool_invocations_used: int = 1
    cpu_seconds_used: float = 0.0


@dataclass(frozen=True)
class CapabilityGrant:
    """Execution-scoped authorization grant token."""

    execution_id: str
    tool_name: str
    granted_capabilities: frozenset[ToolCapability]
    issued_at: float = field(default_factory=time.time)
    expires_at: float | None = None


@dataclass(frozen=True)
class GovernanceRequest:
    """Request submitted to IGovernancePort for admission control."""

    execution_id: str
    node_id: str
    tool_name: str
    required_capabilities: frozenset[ToolCapability]
    resource_request: ResourceRequest
    grant: CapabilityGrant | None = None


@dataclass(frozen=True)
class GovernanceDecision:
    """Immutable admission control decision result."""

    allowed: bool
    reason: str
    execution_id: str
    node_id: str
    tool_name: str
    required_capabilities: frozenset[ToolCapability] = field(default_factory=frozenset)
    granted_capabilities: frozenset[ToolCapability] = field(default_factory=frozenset)
    reservation_id: str | None = None
    decided_at: float = field(default_factory=time.time)
