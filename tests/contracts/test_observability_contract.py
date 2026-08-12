"""Reusable contract test suite for IMetricRecorder, ITracer, IStructuredLogger, and IObservabilityHealth."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.recovery import RecoveryStatus
from nexusai.infrastructure.observability.metrics import PrometheusMetricRecorder
from nexusai.infrastructure.observability.observability_health import ObservabilityHealthService
from nexusai.infrastructure.observability.structured_logging import JSONStructuredLogger
from nexusai.infrastructure.observability.tracing import OpenTelemetryTracer


@pytest.mark.asyncio
async def test_observability_contract_conformance() -> None:
    """Verify observability ports conform to domain contract specifications."""
    metrics = PrometheusMetricRecorder()
    tracer = OpenTelemetryTracer()
    logger = JSONStructuredLogger()
    health = ObservabilityHealthService()

    # Metrics
    metrics.increment_counter("nexusai_execution_total", 1.0, {"tool_id": "process_tool", "status": "success"})
    metrics.record_histogram("nexusai_execution_duration_seconds", 0.05, {"tool_id": "process_tool"})
    assert metrics.counters["nexusai_execution_total"] == 1.0

    # Tracer
    span = tracer.start_span("test_span", {"execution.status": "completed"})
    assert span["name"] == "test_span"

    # Logger
    logger.info("execution_started", tool_id="process_tool")
    assert len(logger.logs) == 1

    # Health
    assert health.is_alive() is True
    assert health.is_ready() is True

    # Quarantined recovery state sets ready = False
    quarantined_health = ObservabilityHealthService(RecoveryStatus.QUARANTINED)
    assert quarantined_health.is_ready() is False


if __name__ == "__main__":
    asyncio.run(test_observability_contract_conformance())
    print("ALL OBSERVABILITY CONTRACT TESTS PASSED SUCCESSFULLY!")
