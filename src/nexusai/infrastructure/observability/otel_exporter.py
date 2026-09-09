"""OpenTelemetry (OTLP) remote trace and metric exporters for distributed observability."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from nexusai.brain.domain.observability import (
    RuntimeEvent,
)
from nexusai.brain.ports.observability_port import IObservabilityPort
from nexusai.infrastructure.observability.in_memory_exporter import (
    sanitize_metric_attributes,
)
from nexusai.infrastructure.observability.redaction import (
    sanitize_secrets_recursive,
)
from nexusai.logging.logger import logger


@dataclass
class OtelSpan:
    """Canonical OpenTelemetry span representation."""

    name: str
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_span_id: str | None = None
    start_time_unix_nano: int = field(default_factory=lambda: int(time.time() * 1_000_000_000))
    end_time_unix_nano: int = field(default_factory=lambda: int(time.time() * 1_000_000_000))
    attributes: dict[str, Any] = field(default_factory=dict)
    status_code: int = 0  # 0: UNSET, 1: OK, 2: ERROR
    status_message: str | None = None

    def __post_init__(self) -> None:
        # Enforce recursive secret sanitization
        self.attributes = sanitize_secrets_recursive(self.attributes)


def _to_otlp_any_value(val: Any) -> dict[str, Any]:
    """Convert a Python value into standard OpenTelemetry AnyValue representation."""
    if isinstance(val, bool):
        return {"boolValue": val}
    elif isinstance(val, int):
        return {"intValue": str(val)}
    elif isinstance(val, float):
        return {"doubleValue": val}
    elif isinstance(val, (list, tuple)):
        return {"arrayValue": {"values": [_to_otlp_any_value(v) for v in val]}}
    elif isinstance(val, dict):
        return {
            "kvlistValue": {
                "values": [{"key": str(k), "value": _to_otlp_any_value(v)} for k, v in val.items()]
            }
        }
    return {"stringValue": str(val)}


def _to_otlp_key_values(attributes: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Convert an attributes map into standard OTLP KeyValue list."""
    return [{"key": k, "value": _to_otlp_any_value(v)} for k, v in attributes.items()]


def parse_otlp_env_headers() -> dict[str, str]:
    """Parse comma-separated key=value pairs from OTEL_EXPORTER_OTLP_HEADERS."""
    raw = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "").strip()
    headers: dict[str, str] = {}
    if not raw:
        return headers
    for pair in raw.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            headers[key.strip()] = value.strip()
    return headers


class OtelTraceExporter:
    """Asynchronous write-behind OpenTelemetry OTLP trace exporter."""

    def __init__(
        self,
        endpoint_url: str | None = None,
        service_name: str | None = None,
        service_version: str = "1.0.0",
        custom_headers: Mapping[str, str] | None = None,
        timeout_seconds: float = 5.0,
        batch_size: int = 50,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if endpoint_url:
            self.endpoint_url = (
                endpoint_url
                if endpoint_url.rstrip("/").endswith("/v1/traces")
                else f"{endpoint_url.rstrip('/')}/v1/traces"
            )
        elif os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
            self.endpoint_url = os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"]
        else:
            base_endpoint = os.getenv(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
            ).rstrip("/")
            self.endpoint_url = f"{base_endpoint}/v1/traces"
        self.service_name = service_name or os.getenv("OTEL_SERVICE_NAME", "nexusai")
        self.service_version = service_version
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size

        env_headers = parse_otlp_env_headers()
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "NexusAI-OtelExporter/1.0",
            **env_headers,
            **dict(custom_headers or {}),
        }

        self._queue: asyncio.Queue[OtelSpan] = asyncio.Queue(maxsize=10000)
        self._http_client = http_client
        self._owns_client = http_client is None
        self._lock = asyncio.Lock()

    def build_otlp_traces_payload(self, spans: Sequence[OtelSpan]) -> dict[str, Any]:
        """Format spans into standard OTLP JSON resourceSpans schema."""
        otlp_spans: list[dict[str, Any]] = []
        for s in spans:
            sanitized_attrs = sanitize_secrets_recursive(s.attributes)
            item: dict[str, Any] = {
                "traceId": s.trace_id,
                "spanId": s.span_id,
                "name": s.name,
                "kind": 1,  # SPAN_KIND_INTERNAL
                "startTimeUnixNano": str(s.start_time_unix_nano),
                "endTimeUnixNano": str(s.end_time_unix_nano),
                "attributes": _to_otlp_key_values(sanitized_attrs),
                "status": {
                    "code": s.status_code,
                    "message": s.status_message or "",
                },
            }
            if s.parent_span_id:
                item["parentSpanId"] = s.parent_span_id
            otlp_spans.append(item)

        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": _to_otlp_key_values(
                            {
                                "service.name": self.service_name,
                                "service.version": self.service_version,
                            }
                        )
                    },
                    "scopeSpans": [
                        {
                            "scope": {
                                "name": "nexusai.tracer",
                                "version": self.service_version,
                            },
                            "spans": otlp_spans,
                        }
                    ],
                }
            ]
        }

    async def enqueue_span(self, span: OtelSpan) -> None:
        """Enqueue span into write-behind buffer without blocking caller (< 0.05ms)."""
        try:
            self._queue.put_nowait(span)
        except asyncio.QueueFull:
            logger.warning(
                "[OtelTraceExporter] Trace buffer is full. Dropping span to prevent memory bloat."
            )

    async def export_batch(self, spans: Sequence[OtelSpan]) -> bool:
        """Send a batch of spans over HTTP POST to the OTLP trace collector."""
        if not spans:
            return True

        payload = self.build_otlp_traces_payload(spans)
        client = self._http_client
        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout_seconds)
            close_client = True

        try:
            response = await client.post(
                self.endpoint_url,
                json=payload,
                headers=self.headers,
            )
            if 200 <= response.status_code < 300:
                return True
            logger.warning(
                f"[OtelTraceExporter] OTLP collector returned status {response.status_code}: {response.text[:200]}"
            )
            return False
        except Exception as exc:
            logger.warning(
                f"[OtelTraceExporter] Failed to export spans to {self.endpoint_url}: {exc}"
            )
            return False
        finally:
            if close_client and client is not None:
                await client.aclose()

    async def flush(self) -> int:
        """Flush all pending queued spans to the OTLP collector."""
        spans_to_export: list[OtelSpan] = []
        while not self._queue.empty():
            try:
                spans_to_export.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not spans_to_export:
            return 0

        async with self._lock:
            for i in range(0, len(spans_to_export), self.batch_size):
                chunk = spans_to_export[i : i + self.batch_size]
                await self.export_batch(chunk)

        return len(spans_to_export)


@dataclass
class MetricPoint:
    """Internal metric observation item."""

    metric_type: str  # counter, gauge, histogram
    name: str
    value: float
    time_unix_nano: int
    attributes: dict[str, str]


class OtelMetricsExporter:
    """Asynchronous write-behind OpenTelemetry OTLP metrics exporter."""

    def __init__(
        self,
        endpoint_url: str | None = None,
        service_name: str | None = None,
        service_version: str = "1.0.0",
        custom_headers: Mapping[str, str] | None = None,
        timeout_seconds: float = 5.0,
        batch_size: int = 100,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if endpoint_url:
            self.endpoint_url = (
                endpoint_url
                if endpoint_url.rstrip("/").endswith("/v1/metrics")
                else f"{endpoint_url.rstrip('/')}/v1/metrics"
            )
        elif os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"):
            self.endpoint_url = os.environ["OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"]
        else:
            base_endpoint = os.getenv(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
            ).rstrip("/")
            self.endpoint_url = f"{base_endpoint}/v1/metrics"
        self.service_name = service_name or os.getenv("OTEL_SERVICE_NAME", "nexusai")
        self.service_version = service_version
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size

        env_headers = parse_otlp_env_headers()
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "NexusAI-OtelExporter/1.0",
            **env_headers,
            **dict(custom_headers or {}),
        }

        self._queue: asyncio.Queue[MetricPoint] = asyncio.Queue(maxsize=20000)
        self._http_client = http_client
        self._owns_client = http_client is None
        self._lock = asyncio.Lock()

    def build_otlp_metrics_payload(self, points: Sequence[MetricPoint]) -> dict[str, Any]:
        """Format metric points into standard OTLP JSON resourceMetrics schema."""
        grouped: dict[str, list[MetricPoint]] = {}
        for p in points:
            grouped.setdefault(p.name, []).append(p)

        otlp_metrics: list[dict[str, Any]] = []
        for name, pts in grouped.items():
            first_type = pts[0].metric_type

            if first_type == "counter":
                data_points = [
                    {
                        "asDouble": p.value,
                        "timeUnixNano": str(p.time_unix_nano),
                        "attributes": _to_otlp_key_values(p.attributes),
                    }
                    for p in pts
                ]
                otlp_metrics.append(
                    {
                        "name": name,
                        "sum": {
                            "dataPoints": data_points,
                            "aggregationTemporality": 2,  # AGGREGATION_TEMPORALITY_CUMULATIVE
                            "isMonotonic": True,
                        },
                    }
                )
            elif first_type == "gauge":
                data_points = [
                    {
                        "asDouble": p.value,
                        "timeUnixNano": str(p.time_unix_nano),
                        "attributes": _to_otlp_key_values(p.attributes),
                    }
                    for p in pts
                ]
                otlp_metrics.append(
                    {
                        "name": name,
                        "gauge": {
                            "dataPoints": data_points,
                        },
                    }
                )
            elif first_type == "histogram":
                data_points = [
                    {
                        "count": 1,
                        "sum": p.value,
                        "timeUnixNano": str(p.time_unix_nano),
                        "attributes": _to_otlp_key_values(p.attributes),
                    }
                    for p in pts
                ]
                otlp_metrics.append(
                    {
                        "name": name,
                        "histogram": {
                            "dataPoints": data_points,
                            "aggregationTemporality": 2,
                        },
                    }
                )

        return {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": _to_otlp_key_values(
                            {
                                "service.name": self.service_name,
                                "service.version": self.service_version,
                            }
                        )
                    },
                    "scopeMetrics": [
                        {
                            "scope": {
                                "name": "nexusai.metrics",
                                "version": self.service_version,
                            },
                            "metrics": otlp_metrics,
                        }
                    ],
                }
            ]
        }

    async def enqueue_metric(
        self,
        metric_type: str,
        name: str,
        value: float,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Sanitize metric labels for cardinality and enqueue observation point."""
        clean_attrs = sanitize_metric_attributes(attributes)
        now_ns = int(time.time() * 1_000_000_000)
        point = MetricPoint(
            metric_type=metric_type,
            name=name,
            value=value,
            time_unix_nano=now_ns,
            attributes=clean_attrs,
        )
        try:
            self._queue.put_nowait(point)
        except asyncio.QueueFull:
            logger.warning(
                "[OtelMetricsExporter] Metric buffer is full. Dropping point to prevent memory bloat."
            )

    async def export_batch(self, points: Sequence[MetricPoint]) -> bool:
        """Send a batch of metric points over HTTP POST to the OTLP metrics collector."""
        if not points:
            return True

        payload = self.build_otlp_metrics_payload(points)
        client = self._http_client
        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout_seconds)
            close_client = True

        try:
            response = await client.post(
                self.endpoint_url,
                json=payload,
                headers=self.headers,
            )
            if 200 <= response.status_code < 300:
                return True
            logger.warning(
                f"[OtelMetricsExporter] OTLP collector returned status {response.status_code}: {response.text[:200]}"
            )
            return False
        except Exception as exc:
            logger.warning(
                f"[OtelMetricsExporter] Failed to export metrics to {self.endpoint_url}: {exc}"
            )
            return False
        finally:
            if close_client and client is not None:
                await client.aclose()

    async def flush(self) -> int:
        """Flush all pending queued metric points to the OTLP collector."""
        points_to_export: list[MetricPoint] = []
        while not self._queue.empty():
            try:
                points_to_export.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not points_to_export:
            return 0

        async with self._lock:
            for i in range(0, len(points_to_export), self.batch_size):
                chunk = points_to_export[i : i + self.batch_size]
                await self.export_batch(chunk)

        return len(points_to_export)


class OtelSpanContext:
    """Context manager wrapping active span execution with duration tracking."""

    def __init__(
        self,
        name: str,
        attributes: Mapping[str, Any] | None = None,
        parent_span_id: str | None = None,
        exporter: OtelTraceExporter | None = None,
    ) -> None:
        self.span = OtelSpan(
            name=name,
            parent_span_id=parent_span_id,
            attributes=dict(attributes or {}),
        )
        self._exporter = exporter

    def set_attribute(self, key: str, value: Any) -> None:
        """Add or update a span attribute."""
        self.span.attributes[key] = value

    def set_status(self, code: int, message: str | None = None) -> None:
        """Set OpenTelemetry status code (0: Unset, 1: OK, 2: Error)."""
        self.span.status_code = code
        self.span.status_message = message

    async def __aenter__(self) -> OtelSpanContext:
        self.span.start_time_unix_nano = int(time.time() * 1_000_000_000)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self.span.end_time_unix_nano = int(time.time() * 1_000_000_000)
        if exc_val is not None:
            self.set_status(2, str(exc_val))
        elif self.span.status_code == 0:
            self.set_status(1)

        if self._exporter is not None:
            await self._exporter.enqueue_span(self.span)


class OtelRemoteExporter(IObservabilityPort):
    """Integrated remote OpenTelemetry telemetry exporter satisfying the IObservabilityPort protocol."""

    def __init__(
        self,
        trace_exporter: OtelTraceExporter | None = None,
        metrics_exporter: OtelMetricsExporter | None = None,
        service_name: str | None = None,
        endpoint_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.trace_exporter = trace_exporter or OtelTraceExporter(
            service_name=service_name,
            endpoint_url=endpoint_url,
            http_client=http_client,
        )
        self.metrics_exporter = metrics_exporter or OtelMetricsExporter(
            service_name=service_name,
            endpoint_url=endpoint_url,
            http_client=http_client,
        )

    def start_span(
        self,
        name: str,
        attributes: Mapping[str, Any] | None = None,
        parent_span_id: str | None = None,
    ) -> OtelSpanContext:
        """Create and return an async context manager for tracing execution spans."""
        return OtelSpanContext(
            name=name,
            attributes=attributes,
            parent_span_id=parent_span_id,
            exporter=self.trace_exporter,
        )

    async def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Increment a metric counter."""
        await self.metrics_exporter.enqueue_metric("counter", name, value, attributes)

    async def record_histogram(
        self,
        name: str,
        value: float,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Record a histogram latency/value observation."""
        await self.metrics_exporter.enqueue_metric("histogram", name, value, attributes)

    async def set_gauge(
        self,
        name: str,
        value: float,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Set a gauge metric value."""
        await self.metrics_exporter.enqueue_metric("gauge", name, value, attributes)

    async def record_gauge(
        self,
        name: str,
        value: float,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Record a gauge metric value."""
        await self.set_gauge(name, value, attributes=attributes)

    async def record_duration(
        self,
        name: str,
        duration_ms: float,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Record a duration sample in milliseconds."""
        await self.record_histogram(name, duration_ms, attributes=attributes)

    async def emit_event(self, event: Any) -> None:
        """Emit an observability telemetry event and convert to an OpenTelemetry span."""
        if isinstance(event, RuntimeEvent):
            start_nano = int(event.timestamp * 1_000_000_000)
            status_code = 2 if "FAILED" in event.event_type.value else 1
            span = OtelSpan(
                name=f"event.{event.event_type.value.lower()}",
                start_time_unix_nano=start_nano,
                end_time_unix_nano=start_nano + 1_000_000,  # 1ms duration for point events
                attributes={
                    "event_id": event.event_id,
                    "event_type": event.event_type.value,
                    "execution_id": event.execution_id or "",
                    "node_id": event.node_id or "",
                    **dict(event.attributes),
                },
                status_code=status_code,
            )
            await self.trace_exporter.enqueue_span(span)

    async def flush(self) -> tuple[int, int]:
        """Flush all pending spans and metric points to OTLP endpoints."""
        spans_flushed = await self.trace_exporter.flush()
        metrics_flushed = await self.metrics_exporter.flush()
        return (spans_flushed, metrics_flushed)
