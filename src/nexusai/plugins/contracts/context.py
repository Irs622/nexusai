"""
Immutable PluginContext container for injecting kernel services into plugins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PluginContext:
    """Immutable runtime context injected into plugins during initialization."""

    plugin_id: str
    logger: Any
    sandbox: Any
    event_bus: Any | None = None
    config_slice: dict[str, Any] = field(default_factory=dict)
    clock: Any | None = None
    cancellation_token: Any | None = None
    metrics: Any | None = None
    container: Any | None = None
    hooks: Any | None = None
