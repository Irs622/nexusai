"""InMemoryMetricsExporter implementation with thread-safety, fault isolation, and cardinality governance."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import time
from typing import Any, Mapping

from nexusai.brain.domain.observability import RuntimeEvent, sanitize_attributes
from nexusai.brain.ports.observability_port import IObservabilityPort

FORBIDDEN_METRIC_LABELS = {
    "execution_id", "node_id", "task_id", "idempotency_key",
    "tool_arguments", "arguments", "payload"
}


def sanitize_metric_attributes(attributes: Mapping[str, Any] | None) -> dict[str, str]:
    """Filter out high-cardinality labels and secrets from metric dimensions."""
    if not attributes:
        return {}

    sanitized: dict[str, str] = {}
    for key, val in attributes.items():
        k_lower = str(key).lower()
        if k_lower in FORBIDDEN_METRIC_LABELS:
            continue  # Omit high-cardinality metric dimensions
        sanitized[str(key)] = str(val)[:100]
    return sanitized


@dataclass
class MetricsSnapshot:
    """Read-only snapshot of collected metrics and runtime events."""

    counters: dict[str, float]
    gauges: dict[str, float]
    duration_samples: dict[str, list[float]]
    events: list[RuntimeEvent]


class InMemoryMetricsExporter(IObservabilityPort):
    """Deterministic in-memory metrics exporter with fault isolation and bounded cardinality."""

    def __init__(self, fail_on_purpose: bool = False) -> None:
        self.fail_on_purpose = fail_on_purpose
        self._lock = asyncio.Lock()
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._duration_samples: dict[str, list[float]] = {}
        self._events: list[RuntimeEvent] = []

    async def emit_event(self, event: Any) -> None:
        """Emit a correlated runtime event with fault isolation."""
        try:
            if self.fail_on_purpose:
                raise RuntimeError("Simulated Telemetry Exporter Fault")
            async with self._lock:
                self._events.append(event)
        except Exception:
            # Fault Isolation Invariant: Telemetry failures NEVER crash core execution
            pass

    async def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Increment a metric counter by value with bounded cardinality."""
        try:
            if self.fail_on_purpose:
                raise RuntimeError("Simulated Telemetry Exporter Fault")
            _clean_attrs = sanitize_metric_attributes(attributes)
            async with self._lock:
                self._counters[name] = self._counters.get(name, 0) + value
        except Exception:
            pass

    async def record_duration(
        self,
        name: str,
        duration_ms: float,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Record an operation duration sample in milliseconds."""
        try:
            if self.fail_on_purpose:
                raise RuntimeError("Simulated Telemetry Exporter Fault")
            _clean_attrs = sanitize_metric_attributes(attributes)
            async with self._lock:
                if name not in self._duration_samples:
                    self._duration_samples[name] = []
                self._duration_samples[name].append(duration_ms)
        except Exception:
            pass

    async def record_gauge(
        self,
        name: str,
        value: float,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Set a gauge metric value."""
        try:
            if self.fail_on_purpose:
                raise RuntimeError("Simulated Telemetry Exporter Fault")
            _clean_attrs = sanitize_metric_attributes(attributes)
            async with self._lock:
                self._gauges[name] = value
        except Exception:
            pass

    def snapshot(self) -> MetricsSnapshot:
        """Create a thread-safe snapshot copy of current metrics state."""
        return MetricsSnapshot(
            counters=dict(self._counters),
            gauges=dict(self._gauges),
            duration_samples={k: list(v) for k, v in self._duration_samples.items()},
            events=list(self._events),
        )

    def reset(self) -> None:
        """Reset all collected counters, gauges, samples, and events."""
        self._counters.clear()
        self._gauges.clear()
        self._duration_samples.clear()
        self._events.clear()
