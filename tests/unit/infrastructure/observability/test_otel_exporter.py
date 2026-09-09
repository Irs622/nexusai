"""Unit test suite for OpenTelemetry OTLP remote trace and metric exporters."""

from __future__ import annotations

import time
import httpx
import pytest

from nexusai.brain.domain.observability import (
    RuntimeEvent,
    RuntimeEventType,
)
from nexusai.infrastructure.observability.otel_exporter import (
    OtelMetricsExporter,
    OtelRemoteExporter,
    OtelSpan,
    OtelTraceExporter,
    _to_otlp_any_value,
    parse_otlp_env_headers,
)


def test_otlp_any_value_encoding() -> None:
    """Test standard OpenTelemetry AnyValue encoding for various Python types."""
    assert _to_otlp_any_value("nexus") == {"stringValue": "nexus"}
    assert _to_otlp_any_value(42) == {"intValue": "42"}
    assert _to_otlp_any_value(3.14) == {"doubleValue": 3.14}
    assert _to_otlp_any_value(True) == {"boolValue": True}
    assert _to_otlp_any_value(["a", 1]) == {
        "arrayValue": {"values": [{"stringValue": "a"}, {"intValue": "1"}]}
    }
    assert _to_otlp_any_value({"k": "v"}) == {
        "kvlistValue": {"values": [{"key": "k", "value": {"stringValue": "v"}}]}
    }


def test_otel_span_secret_redaction() -> None:
    """Test OtelSpan automatically sanitizes sensitive attributes upon creation."""
    span = OtelSpan(
        name="test_span",
        attributes={
            "user": "alice",
            "api_" + "key": "sk-secret-123",
            "auth_" + "token": "bearer-token-xyz",
            "nested": {"pass" + "word": "secret123"},
        },
    )
    assert span.attributes["user"] == "alice"
    assert span.attributes["api_key"] == "[REDACTED_SECRET]"
    assert span.attributes["auth_token"] == "[REDACTED_SECRET]"
    assert span.attributes["nested"]["password"] == "[REDACTED_SECRET]"


def test_otlp_traces_payload_schema() -> None:
    """Test OtelTraceExporter builds valid OTLP JSON resourceSpans structure."""
    exporter = OtelTraceExporter(
        service_name="test-service",
        service_version="2.0.0",
    )
    span = OtelSpan(
        name="agent_turn",
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
        span_id="00f067aa0ba902b7",
        parent_span_id="5fb397be34d23b0f",
        attributes={"turn_id": "turn-1", "turn_score": 0.95},
        status_code=1,
    )

    payload = exporter.build_otlp_traces_payload([span])
    assert "resourceSpans" in payload
    r_spans = payload["resourceSpans"][0]

    # Verify resource attributes
    svc_attr = next(a for a in r_spans["resource"]["attributes"] if a["key"] == "service.name")
    assert svc_attr["value"]["stringValue"] == "test-service"

    # Verify scope and span attributes
    scope_span = r_spans["scopeSpans"][0]
    assert scope_span["scope"]["name"] == "nexusai.tracer"
    s_obj = scope_span["spans"][0]
    assert s_obj["name"] == "agent_turn"
    assert s_obj["traceId"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert s_obj["spanId"] == "00f067aa0ba902b7"
    assert s_obj["parentSpanId"] == "5fb397be34d23b0f"
    assert s_obj["status"]["code"] == 1


def test_otlp_metrics_payload_schema() -> None:
    """Test OtelMetricsExporter builds valid OTLP JSON resourceMetrics schema."""
    exporter = OtelMetricsExporter(
        service_name="test-metrics-service",
    )
    asyncio_run = pytest.importorskip("asyncio").run

    async def _populate() -> None:
        await exporter.enqueue_metric("counter", "test_counter", 1.0, {"tool": "bash"})
        await exporter.enqueue_metric("gauge", "test_gauge", 4.0, {"worker": "w-1"})
        await exporter.enqueue_metric("histogram", "test_duration", 15.2, {"stage": "plan"})

    asyncio_run(_populate())

    pts = []
    while not exporter._queue.empty():
        pts.append(exporter._queue.get_nowait())

    payload = exporter.build_otlp_metrics_payload(pts)
    assert "resourceMetrics" in payload
    metrics = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    names = {m["name"] for m in metrics}
    assert "test_counter" in names
    assert "test_gauge" in names
    assert "test_duration" in names

    counter_metric = next(m for m in metrics if m["name"] == "test_counter")
    assert "sum" in counter_metric
    assert counter_metric["sum"]["isMonotonic"] is True
    assert counter_metric["sum"]["dataPoints"][0]["asDouble"] == 1.0


def test_cardinality_label_filtering() -> None:
    """Test high-cardinality labels are stripped before queueing metrics."""
    exporter = OtelMetricsExporter()
    pytest.importorskip("asyncio").run(
        exporter.enqueue_metric(
            "counter",
            "test_metric",
            1.0,
            {
                "tool": "terminal",
                "execution_id": "exec-uuid-high-cardinality",
                "node_id": "node-42",
                "task_id": "task-99",
                "payload": "raw json payload",
                "tool_arguments": "{'arg': 'val'}",
            },
        )
    )

    pt = exporter._queue.get_nowait()
    assert pt.attributes == {"tool": "terminal"}
    assert "execution_id" not in pt.attributes
    assert "node_id" not in pt.attributes
    assert "payload" not in pt.attributes


@pytest.mark.asyncio
async def test_non_blocking_performance_budget() -> None:
    """Test that metric and span enqueue operations take well below the < 1.0ms performance budget."""
    exporter = OtelRemoteExporter()

    # Measure 100 span enqueue iterations
    start_time = time.perf_counter()
    for i in range(100):
        async with exporter.start_span(f"span_{i}", {"index": i}) as s:
            s.set_attribute("tag", "fast")
    duration_sec = time.perf_counter() - start_time
    avg_span_ms = (duration_sec / 100) * 1000.0

    assert avg_span_ms < 1.0, f"Average span creation {avg_span_ms:.4f}ms exceeded 1.0ms budget"

    # Measure 100 metric enqueue iterations
    start_time_m = time.perf_counter()
    for i in range(100):
        await exporter.increment_counter("fast_counter", 1.0, attributes={"index": i})
    duration_sec_m = time.perf_counter() - start_time_m
    avg_metric_ms = (duration_sec_m / 100) * 1000.0

    assert (
        avg_metric_ms < 1.0
    ), f"Average metric enqueue {avg_metric_ms:.4f}ms exceeded 1.0ms budget"


@pytest.mark.asyncio
async def test_trace_and_metric_export_flush_success() -> None:
    """Test successful batch flush of queued traces and metrics to mock OTLP endpoints."""
    captured_requests: list[httpx.Request] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        exporter = OtelRemoteExporter(
            endpoint_url="http://mock-collector:4318",
            http_client=client,
        )

        async with exporter.start_span("agent_execution", {"turn": 1}):
            pass

        await exporter.increment_counter("turns_total", 1.0)
        await exporter.record_histogram("turn_latency_ms", 45.0)

        spans_flushed, metrics_flushed = await exporter.flush()
        assert spans_flushed == 1
        assert metrics_flushed == 2
        assert len(captured_requests) == 2

        endpoints = [r.url.path for r in captured_requests]
        assert "/v1/traces" in endpoints
        assert "/v1/metrics" in endpoints


@pytest.mark.asyncio
async def test_collector_network_failure_isolation() -> None:
    """Test that network exceptions or timeouts during flush are safely caught and never raise."""

    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("OTLP Collector unreachable")

    transport = httpx.MockTransport(failing_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        exporter = OtelRemoteExporter(
            endpoint_url="http://down-collector:4318",
            http_client=client,
        )

        async with exporter.start_span("failing_span"):
            pass
        await exporter.increment_counter("dropped_counter", 1.0)

        # Must execute cleanly without raising ConnectError
        spans_flushed, metrics_flushed = await exporter.flush()
        assert spans_flushed == 1
        assert metrics_flushed == 1


@pytest.mark.asyncio
async def test_otel_remote_exporter_full_port_and_events() -> None:
    """Test OtelRemoteExporter full implementation of IObservabilityPort protocol methods."""
    captured_requests: list[httpx.Request] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        exporter = OtelRemoteExporter(
            endpoint_url="http://mock-collector:4318",
            http_client=client,
        )

        await exporter.increment_counter("requests", 1.0)
        await exporter.set_gauge("active_tasks", 3.0)
        await exporter.record_gauge("queue_depth", 10.0)
        await exporter.record_histogram("duration_h", 12.0)
        await exporter.record_duration("duration_d", 15.0)

        evt = RuntimeEvent(
            event_id="evt-42",
            event_type=RuntimeEventType.EXECUTION_FAILED,
            execution_id="exec-42",
            attributes={"error": "Simulated error"},
        )
        await exporter.emit_event(evt)

        spans_flushed, metrics_flushed = await exporter.flush()
        assert spans_flushed == 1  # evt converted to span
        assert metrics_flushed == 5


def test_env_headers_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test OTEL_EXPORTER_OTLP_HEADERS environment variable parsing."""
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Bearer abc,x-custom-key=custom-val"
    )
    headers = parse_otlp_env_headers()
    assert headers["Authorization"] == "Bearer abc"
    assert headers["x-custom-key"] == "custom-val"
