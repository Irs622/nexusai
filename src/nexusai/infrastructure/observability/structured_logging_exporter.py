"""StructuredLoggingExporter implementation outputting JSON machine-readable logs with secret redaction."""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Mapping, TextIO

from nexusai.brain.domain.observability import RuntimeEvent, sanitize_attributes
from nexusai.brain.ports.observability_port import IObservabilityPort


class StructuredLoggingExporter(IObservabilityPort):
    """Machine-readable JSON event stream exporter with secret redaction and fault isolation."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout

    def _write_json(self, payload: dict[str, Any]) -> None:
        """Write JSON payload to output stream with fault isolation."""
        try:
            line = json.dumps(payload)
            self.stream.write(line + "\n")
            self.stream.flush()
        except Exception:
            # Fault Isolation: Stream write failures NEVER break core execution
            pass

    async def emit_event(self, event: Any) -> None:
        """Emit JSON structured log record for a RuntimeEvent."""
        payload = {
            "timestamp": event.timestamp,
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "execution_id": event.execution_id,
            "node_id": event.node_id,
            "task_id": event.task_id,
            "attempt": event.attempt,
            "attributes": sanitize_attributes(event.attributes),
        }
        self._write_json(payload)

    async def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Emit JSON structured record for counter increment."""
        payload = {
            "timestamp": time.time(),
            "metric_type": "counter",
            "metric_name": name,
            "value": value,
            "attributes": sanitize_attributes(attributes),
        }
        self._write_json(payload)

    async def record_duration(
        self,
        name: str,
        duration_ms: float,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Emit JSON structured record for duration sample."""
        payload = {
            "timestamp": time.time(),
            "metric_type": "duration",
            "metric_name": name,
            "duration_ms": duration_ms,
            "attributes": sanitize_attributes(attributes),
        }
        self._write_json(payload)

    async def record_gauge(
        self,
        name: str,
        value: float,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Emit JSON structured record for gauge value."""
        payload = {
            "timestamp": time.time(),
            "metric_type": "gauge",
            "metric_name": name,
            "value": value,
            "attributes": sanitize_attributes(attributes),
        }
        self._write_json(payload)
