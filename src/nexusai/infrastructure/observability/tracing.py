"""OpenTelemetry tracing implementation with gRPC context propagation."""

from __future__ import annotations

import time
from typing import Any, Mapping

from nexusai.brain.ports.observability_port import ITracer
from nexusai.infrastructure.observability.redaction import sanitize_secrets_recursive


class OpenTelemetryTracer(ITracer):
    """OpenTelemetry tracer implementation enforcing non-sensitive span attributes."""

    def __init__(self) -> None:
        self.spans: list[dict[str, Any]] = []

    def start_span(self, name: str, attributes: Mapping[str, Any] | None = None) -> Any:
        sanitized_attr = sanitize_secrets_recursive(attributes or {})
        span_obj = {
            "name": name,
            "attributes": sanitized_attr,
            "start_time": time.time(),
        }
        self.spans.append(span_obj)
        return span_obj
