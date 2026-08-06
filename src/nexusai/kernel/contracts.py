"""
Kernel service contracts, lifecycle states, and descriptors for NexusAI OS Kernel.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ServiceLifecycleState(str, Enum):
    """Lifecycle states of kernel services."""

    UNINITIALIZED = "UNINITIALIZED"
    INITIALIZED = "INITIALIZED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    ROLLING_BACK = "ROLLING_BACK"


@dataclass(frozen=True)
class ServiceDescriptor:
    """Immutable descriptor container for kernel service identification and metadata."""

    id: str
    name: str
    version: str
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    state: ServiceLifecycleState = ServiceLifecycleState.UNINITIALIZED


class KernelService(ABC):
    """Abstract base class for all NexusAI OS kernel services."""

    def __init__(self, descriptor: ServiceDescriptor) -> None:
        self._descriptor = descriptor
        self._state = descriptor.state

    @property
    def descriptor(self) -> ServiceDescriptor:
        """Return the service descriptor metadata."""
        return self._descriptor

    @property
    def service_id(self) -> str:
        """Return unique service ID."""
        return self._descriptor.id

    @property
    def state(self) -> ServiceLifecycleState:
        """Return current service lifecycle state."""
        return self._state

    def set_state(self, new_state: ServiceLifecycleState) -> None:
        """Update the internal lifecycle state of the service."""
        self._state = new_state

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize service resources before startup."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start service execution."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop service execution and release active runtime handlers."""
        pass

    async def shutdown(self) -> None:
        """Perform full cleanup and final resource deallocation upon system shutdown."""
        await self.stop()

    # Kubernetes-style Probes & Observability APIs
    async def health(self) -> dict[str, Any]:
        """Return health status dictionary."""
        return {
            "service_id": self.service_id,
            "state": self._state.value,
            "healthy": self._state == ServiceLifecycleState.RUNNING,
        }

    async def readiness(self) -> bool:
        """Readiness probe: return True if service is ready to accept traffic."""
        return self._state == ServiceLifecycleState.RUNNING

    async def liveness(self) -> bool:
        """Liveness probe: return True if service process is alive and not failed."""
        return self._state not in (ServiceLifecycleState.FAILED, ServiceLifecycleState.STOPPED)

    async def metrics(self) -> dict[str, Any]:
        """Return telemetry metrics dictionary."""
        return {
            "service_id": self.service_id,
            "uptime_status": self._state.value,
        }
