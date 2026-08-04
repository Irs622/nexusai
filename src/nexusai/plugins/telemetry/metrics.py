"""
MetricsInterface for plugin telemetry and monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Sequence


@dataclass(frozen=True)
class MetricRecord:
    """Telemetry metric data record."""

    name: str
    kind: str  # counter, gauge, timer
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: dict[str, str] = field(default_factory=dict)


class MetricsInterface:
    """Unified telemetry metrics collection interface for plugins."""

    def __init__(self) -> None:
        self._records: list[MetricRecord] = []

    def counter(self, name: str, value: float = 1.0, **tags: str) -> None:
        """Increment a metric counter."""
        self._records.append(MetricRecord(name=name, kind="counter", value=value, tags=tags))

    def gauge(self, name: str, value: float, **tags: str) -> None:
        """Record a gauge metric value."""
        self._records.append(MetricRecord(name=name, kind="gauge", value=value, tags=tags))

    def timer(self, name: str, duration_seconds: float, **tags: str) -> None:
        """Record execution duration in seconds."""
        self._records.append(MetricRecord(name=name, kind="timer", value=duration_seconds, tags=tags))

    def get_records(self) -> Sequence[MetricRecord]:
        """Return collected metric records."""
        return list(self._records)

    def clear(self) -> None:
        """Clear recorded metrics."""
        self._records.clear()
