"""Protocol port interfaces for production observability, metrics, distributed tracing, structured logging, and health signals."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class IMetricRecorder(Protocol):
    """Protocol interface for Prometheus-compatible metric recording with strict cardinality bounds."""

    def increment_counter(self, name: str, value: float = 1.0, labels: Mapping[str, str] | None = None) -> None:
        """Increment a counter metric."""
        ...

    def record_histogram(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        """Record a histogram latency/value observation."""
        ...

    def set_gauge(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        """Set a gauge metric value."""
        ...


@runtime_checkable
class ITracer(Protocol):
    """Protocol interface for OpenTelemetry distributed tracing."""

    def start_span(self, name: str, attributes: Mapping[str, Any] | None = None) -> Any:
        """Start a new trace span with non-sensitive attributes."""
        ...


@runtime_checkable
class IStructuredLogger(Protocol):
    """Protocol interface for JSON structured logging with automatic secret redaction."""

    def info(self, event: str, **kwargs: Any) -> None:
        """Log INFO level structured event."""
        ...

    def error(self, event: str, **kwargs: Any) -> None:
        """Log ERROR level structured event."""
        ...


@runtime_checkable
class IObservabilityHealth(Protocol):
    """Protocol interface for readiness and liveness health probes."""

    def is_alive(self) -> bool:
        """Return True if application process is alive."""
        ...

    def is_ready(self) -> bool:
        """Return True if application dependencies and disaster recovery state permit accepting traffic."""
        ...


@runtime_checkable
class IObservabilityPort(Protocol):
    """Aggregate protocol interface combining metric recording, tracing, structured logging, and health probes."""

    async def increment_counter(self, name: str, value: float = 1.0, *, attributes: Mapping[str, Any] | None = None) -> None:
        """Increment a counter metric."""
        ...

    async def record_histogram(self, name: str, value: float, attributes: Mapping[str, Any] | None = None) -> None:
        """Record a histogram latency/value observation."""
        ...

    async def set_gauge(self, name: str, value: float, attributes: Mapping[str, Any] | None = None) -> None:
        """Set a gauge metric value."""
        ...

    async def record_gauge(self, name: str, value: float, *, attributes: Mapping[str, Any] | None = None) -> None:
        """Record a gauge metric value."""
        ...

    async def record_duration(self, name: str, duration_ms: float, *, attributes: Mapping[str, Any] | None = None) -> None:
        """Record a duration metric value."""
        ...

    async def emit_event(self, event: Any) -> None:
        """Emit an observability telemetry event."""
        ...




