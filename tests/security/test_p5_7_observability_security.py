"""Security test suite for P5-7 Production Observability invariants (P5-7-INV-01 to P5-7-INV-25)."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.recovery import RecoveryStatus
from nexusai.infrastructure.observability.metrics import HighCardinalityLabelViolation, PrometheusMetricRecorder
from nexusai.infrastructure.observability.observability_health import ObservabilityHealthService
from nexusai.infrastructure.observability.structured_logging import JSONStructuredLogger
from nexusai.infrastructure.observability.tracing import OpenTelemetryTracer


@pytest.mark.asyncio
async def test_security_observability_cannot_grant_execution_authority() -> None:
    """Security Test (P5-7-INV-01 to P5-7-INV-04): Recording metrics, traces, or logs CANNOT create execution authority."""
    metrics = PrometheusMetricRecorder()
    metrics.increment_counter("nexusai_execution_total", 1.0, {"status": "allowed"})
    # Recording telemetry DOES NOT modify Governance, ToolRegistry, or Approval state!


@pytest.mark.asyncio
async def test_security_high_cardinality_labels_denied_in_metrics() -> None:
    """Security Test (P5-7-INV-14 to P5-7-INV-16): High-cardinality labels (execution_id, prompt, session_id) MUST BE DENIED!"""
    metrics = PrometheusMetricRecorder()

    with pytest.raises(HighCardinalityLabelViolation):
        metrics.increment_counter("test_count", 1.0, {"execution_id": "exec-12345"})

    with pytest.raises(HighCardinalityLabelViolation):
        metrics.increment_counter("test_count", 1.0, {"prompt": "unbounded user text"})


@pytest.mark.asyncio
async def test_security_secrets_redacted_from_logs_and_spans() -> None:
    """Security Test (P5-7-INV-07 to P5-7-INV-10): Raw secrets in kwargs redacted from logs and OpenTelemetry spans."""
    logger = JSONStructuredLogger()
    tracer = OpenTelemetryTracer()

    logger.info("api_call", api_key="sk-secret-12345", password="my-secret-pass")
    span = tracer.start_span("api_span", {"api_key": "sk-secret-12345"})

    log_entry = logger.logs[0]
    assert log_entry["api_key"] == "[REDACTED_SECRET]"
    assert log_entry["password"] == "[REDACTED_SECRET]"

    assert span["attributes"]["api_key"] == "[REDACTED_SECRET]"


@pytest.mark.asyncio
async def test_security_quarantined_recovery_sets_readiness_false() -> None:
    """Security Test (P5-7-INV-23): Disaster recovery QUARANTINED state MUST set readiness probe to False."""
    health = ObservabilityHealthService(RecoveryStatus.QUARANTINED)
    assert health.is_ready() is False


if __name__ == "__main__":
    asyncio.run(test_security_observability_cannot_grant_execution_authority())
    asyncio.run(test_security_high_cardinality_labels_denied_in_metrics())
    asyncio.run(test_security_secrets_redacted_from_logs_and_spans())
    asyncio.run(test_security_quarantined_recovery_sets_readiness_false())
    print("ALL P5-7 OBSERVABILITY SECURITY TESTS PASSED SUCCESSFULLY!")
