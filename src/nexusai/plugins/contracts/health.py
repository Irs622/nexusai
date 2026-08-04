"""
Plugin Health check interface and HealthStatus definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HealthStatus(str, Enum):
    """Plugin health status enumeration."""

    READY = "READY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PluginHealth:
    """Plugin health report model."""

    status: HealthStatus
    message: str = "Plugin operating normally"
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ready(cls, message: str = "Plugin operating normally", **diagnostics: Any) -> PluginHealth:
        """Create a READY health status report."""
        return cls(status=HealthStatus.READY, message=message, diagnostics=diagnostics)

    @classmethod
    def degraded(cls, message: str, **diagnostics: Any) -> PluginHealth:
        """Create a DEGRADED health status report."""
        return cls(status=HealthStatus.DEGRADED, message=message, diagnostics=diagnostics)

    @classmethod
    def failed(cls, message: str, **diagnostics: Any) -> PluginHealth:
        """Create a FAILED health status report."""
        return cls(status=HealthStatus.FAILED, message=message, diagnostics=diagnostics)
