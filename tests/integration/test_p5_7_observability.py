"""Observability integration test suite for P5-7."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.infrastructure.observability.metrics import PrometheusMetricRecorder
from nexusai.infrastructure.observability.observability_health import ObservabilityHealthService
from nexusai.infrastructure.observability.structured_logging import JSONStructuredLogger
from nexusai.infrastructure.observability.tracing import OpenTelemetryTracer


@pytest.mark.asyncio
async def test_full_observability_pipeline_integration() -> None:
    """Integration Test: Full execution telemetry pipeline recording metrics, spans, and structured logs."""
    metrics = PrometheusMetricRecorder()
    tracer = OpenTelemetryTracer()
    logger = JSONStructuredLogger()
    health = ObservabilityHealthService()

    # Record full lifecycle metrics
    metrics.increment_counter("nexusai_execution_total", 1.0, {"tool_id": "process_tool", "status": "success"})
    span = tracer.start_span("execution_pipeline", {"tool_id": "process_tool"})
    logger.info("execution_completed", tool_id="process_tool", duration_ms=45.2)

    assert metrics.counters["nexusai_execution_total"] == 1.0
    assert len(tracer.spans) == 1
    assert len(logger.logs) == 1
    assert health.is_ready() is True


if __name__ == "__main__":
    asyncio.run(test_full_observability_pipeline_integration())
    print("ALL OBSERVABILITY INTEGRATION TESTS PASSED SUCCESSFULLY!")
