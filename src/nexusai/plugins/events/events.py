"""
Plugin domain event models for Pub/Sub EventBus integration.
"""

from __future__ import annotations

import time
import uuid

from pydantic import BaseModel, Field

from nexusai.plugins.contracts.state import PluginState


class PluginDomainEvent(BaseModel):
    """Base domain event for all plugin operations."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=time.time)
    correlation_id: str | None = Field(default=None)
    causation_id: str | None = Field(default=None)
    plugin_id: str

    model_config = {
        "frozen": True,
        "arbitrary_types_allowed": True,
    }


class PluginDiscoveredEvent(PluginDomainEvent):
    """Emitted when a plugin candidate is discovered."""

    location: str
    manifest_format: str = "yaml"


class PluginLoadedEvent(PluginDomainEvent):
    """Emitted when a plugin module and instance are loaded into memory."""

    version: str
    capabilities: list[str] = Field(default_factory=list)


class PluginStartedEvent(PluginDomainEvent):
    """Emitted when a plugin lifecycle transitions to ACTIVE."""

    capabilities: list[str] = Field(default_factory=list)


class PluginStoppedEvent(PluginDomainEvent):
    """Emitted when a plugin is stopped."""

    reason: str = "normal_shutdown"


class PluginFailedEvent(PluginDomainEvent):
    """Emitted when a plugin encounters a failure during lifecycle operations."""

    error: str
    failed_state: PluginState


class PluginReloadedEvent(PluginDomainEvent):
    """Emitted when a plugin is reloaded."""

    old_checksum: str
    new_checksum: str


class CapabilityRegisteredEvent(PluginDomainEvent):
    """Emitted when a capability is registered in PluginRegistry."""

    capability_name: str
    capability_version: str
