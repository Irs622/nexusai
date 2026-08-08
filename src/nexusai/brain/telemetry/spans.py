"""OpenTelemetry-compatible ExecutionSpan and TraceCollector for end-to-end runtime observability."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(frozen=True)
class ExecutionSpan:
    """Observability execution span representing a sub-operation duration and breakdown.

    Attributes:
        span_id: Unique span UUID string.
        parent_span_id: Optional parent span UUID.
        name: Operation span name (e.g. "planner.plan", "tool.execute").
        start_time: Start epoch timestamp float.
        end_time: End epoch timestamp float.
        duration_ms: Calculated duration in milliseconds.
        attributes: Attribute key-value map.
        status: Status string ("OK" or "ERROR").
    """

    name: str
    span_id: str = field(default_factory=lambda: str(uuid4()))
    parent_span_id: str | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    duration_ms: float = 0.0
    attributes: dict[str, str] = field(default_factory=dict)
    status: str = "OK"


class TraceCollector:
    """Collects execution timeline spans and provides latency breakdown analytics."""

    def __init__(self) -> None:
        self.spans: list[ExecutionSpan] = []

    def record_span(self, span: ExecutionSpan) -> None:
        """Record a completed ExecutionSpan."""
        self.spans.append(span)

    def get_latency_breakdown(self) -> dict[str, float]:
        """Return aggregated latency breakdown by span operation name."""
        breakdown: dict[str, float] = {}
        for s in self.spans:
            breakdown[s.name] = breakdown.get(s.name, 0.0) + s.duration_ms
        return breakdown
