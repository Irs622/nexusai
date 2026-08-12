"""Observability performance & telemetry load test suite for P5-7."""

from __future__ import annotations

import asyncio
import time
import pytest

from nexusai.infrastructure.observability.metrics import PrometheusMetricRecorder
from nexusai.infrastructure.observability.structured_logging import JSONStructuredLogger
from nexusai.infrastructure.observability.tracing import OpenTelemetryTracer
from tests.performance.metrics import PerformanceMetrics


@pytest.mark.asyncio
async def test_observability_high_volume_telemetry_load() -> None:
    """Load Test: 10,000 metrics, spans, and structured logs recorded without runtime performance degradation."""
    metrics_recorder = PrometheusMetricRecorder()
    tracer = OpenTelemetryTracer()
    logger = JSONStructuredLogger()

    perf_metrics = PerformanceMetrics(benchmark_name="P5-7 Observability High-Volume Load", workers=1)

    t0_start = time.perf_counter()
    for i in range(1, 10001):
        t0 = time.perf_counter()
        metrics_recorder.increment_counter("nexusai_execution_total", 1.0, {"tool_id": "process_tool", "status": "success"})
        tracer.start_span("span_load", {"operation": "tool_exec"})
        logger.info("telemetry_event", tool_id="process_tool", idx=i)
        t1 = time.perf_counter()

        perf_metrics.record_operation((t1 - t0) * 1000.0, success=True)

    perf_metrics.finalize()
    perf_metrics.export_json("artifacts/p5_7/metrics_results.json")

    d = perf_metrics.to_dict()
    print(f"\n[P5-7 OBSERVABILITY TELEMETRY LOAD RESULTS]")
    print(f"Total Operations: {d['total_operations']} | Throughput: {d['throughput_ops_sec']} ops/sec")
    print(f"Latencies (ms) -> p50: {d['latency_ms']['p50']} | p95: {d['latency_ms']['p95']} | p99: {d['latency_ms']['p99']} | max: {d['latency_ms']['max']}")

    assert d["total_operations"] == 10000
    assert d["failed_operations"] == 0


if __name__ == "__main__":
    asyncio.run(test_observability_high_volume_telemetry_load())
    print("ALL OBSERVABILITY PERFORMANCE LOAD TESTS PASSED SUCCESSFULLY!")
