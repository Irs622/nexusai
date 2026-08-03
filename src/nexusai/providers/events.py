"""Events emitted across the Provider SDK lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from nexusai.core.annotations import stable


@stable
@dataclass(frozen=True)
class ProviderEvent:
    """Base event for all Provider SDK telemetry and lifecycle events."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@stable
@dataclass(frozen=True)
class ProviderRegisteredEvent(ProviderEvent):
    """Emitted when a new provider is registered in the registry."""

    provider_id: str = ""
    display_name: str = ""


@stable
@dataclass(frozen=True)
class ProviderUnregisteredEvent(ProviderEvent):
    """Emitted when a provider is unregistered from the registry."""

    provider_id: str = ""


@stable
@dataclass(frozen=True)
class ProviderHealthChangedEvent(ProviderEvent):
    """Emitted when a provider's health state changes."""

    provider_id: str = ""
    healthy: bool = True
    latency_ms: float = 0.0
    error: str | None = None


@stable
@dataclass(frozen=True)
class RoutingDecisionEvent(ProviderEvent):
    """Emitted when ProviderRouter makes a routing decision."""

    selected_provider_id: str = ""
    score: float = 1.0
    reason: str = ""
