"""Distributed Tracing and Observability Spans for request profiling."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from nexusai.core.annotations import stable


@stable
@dataclass
class Span:
    """Lightweight timing span recording execution segments."""

    name: str
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    def finish(self) -> None:
        """Mark span as finished and calculate duration."""
        self.duration_ms = (time.time() - self.start_time) * 1000.0


@stable
class Trace:
    """Distributed trace container aggregating nested timing spans for OpenTelemetry compatibility."""

    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or str(uuid.uuid4())
        self.spans: list[Span] = []

    def start_span(self, name: str, parent_span_id: str | None = None, **attributes: Any) -> Span:
        """Create and record a new timing span."""
        span = Span(name=name, parent_span_id=parent_span_id, attributes=attributes)
        self.spans.append(span)
        return span
