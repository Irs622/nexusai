"""
OpenTelemetry-compatible distributed tracer for NexusAI kernel and plugins.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpanContext:
    """Distributed tracing context containing trace_id, span_id, and parent_span_id."""

    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])
    parent_span_id: str | None = None


@dataclass
class TraceSpan:
    """OpenTelemetry-compatible trace span representation."""

    name: str
    context: SpanContext
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "OK"  # OK, ERROR
    error_message: str | None = None

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a span attribute key-value pair."""
        self.attributes[key] = value

    def end(self, status: str = "OK", error_message: str | None = None) -> None:
        """Close trace span execution."""
        self.end_time = time.time()
        self.status = status
        self.error_message = error_message

    @property
    def duration_ms(self) -> float:
        """Return span execution duration in milliseconds."""
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000.0


class NexusTracer:
    """Distributed OpenTelemetry-compatible tracer."""

    def __init__(self) -> None:
        self._spans: list[TraceSpan] = []

    def start_span(
        self,
        name: str,
        parent_context: SpanContext | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> TraceSpan:
        """Start a new trace span with parent propagation."""
        trace_id = parent_context.trace_id if parent_context else str(uuid.uuid4())
        parent_span_id = parent_context.span_id if parent_context else None

        context = SpanContext(trace_id=trace_id, parent_span_id=parent_span_id)
        span = TraceSpan(name=name, context=context, attributes=attributes or {})
        self._spans.append(span)
        return span

    def get_spans(self) -> list[TraceSpan]:
        """Return list of all created trace spans."""
        return list(self._spans)

    def clear(self) -> None:
        """Clear recorded trace spans."""
        self._spans.clear()
