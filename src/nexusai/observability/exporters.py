"""
Telemetry and trace exporters (ConsoleExporter, JSONFileExporter, OpenTelemetryExporter).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
from pathlib import Path
from typing import Any, Sequence

from nexusai.observability.metrics import TokenLatencyMetric
from nexusai.observability.tracer import TraceSpan


class TelemetryExporter(ABC):
    """Abstract telemetry exporter interface."""

    @abstractmethod
    def export_spans(self, spans: Sequence[TraceSpan]) -> None:
        """Export trace spans."""
        pass

    @abstractmethod
    def export_metrics(self, metrics: Sequence[TokenLatencyMetric]) -> None:
        """Export token latency metrics."""
        pass


class ConsoleExporter(TelemetryExporter):
    """Prints trace spans and metrics to stdout/console."""

    def export_spans(self, spans: Sequence[TraceSpan]) -> None:
        for span in spans:
            print(f"[TRACE] {span.name} (Duration: {span.duration_ms:.2f}ms, Status: {span.status})")

    def export_metrics(self, metrics: Sequence[TokenLatencyMetric]) -> None:
        for m in metrics:
            print(
                f"[METRIC] Provider: {m.provider} | Model: {m.model} | "
                f"TTFT: {m.time_to_first_token_ms:.2f}ms | TPS: {m.tokens_per_second:.2f} tok/s"
            )


class JSONFileExporter(TelemetryExporter):
    """Exports trace spans and metrics to JSON log file."""

    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path

    def export_spans(self, spans: Sequence[TraceSpan]) -> None:
        data = [
            {
                "name": s.name,
                "trace_id": s.context.trace_id,
                "span_id": s.context.span_id,
                "duration_ms": s.duration_ms,
                "status": s.status,
                "attributes": s.attributes,
            }
            for s in spans
        ]
        self._append_json({"type": "spans", "data": data})

    def export_metrics(self, metrics: Sequence[TokenLatencyMetric]) -> None:
        data = [
            {
                "provider": m.provider,
                "model": m.model,
                "ttft_ms": m.time_to_first_token_ms,
                "total_duration_ms": m.total_duration_ms,
                "tokens_per_sec": m.tokens_per_second,
            }
            for m in metrics
        ]
        self._append_json({"type": "metrics", "data": data})

    def _append_json(self, payload: dict[str, Any]) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
