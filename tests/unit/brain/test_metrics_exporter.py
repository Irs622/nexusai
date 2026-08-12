"""Unit tests for InMemoryMetricsExporter, StructuredLoggingExporter, fault isolation, and cardinality rules."""

from __future__ import annotations

import io
import json
import asyncio
import pytest

from nexusai.brain.domain.observability import RuntimeEvent, RuntimeEventType
from nexusai.infrastructure.observability.in_memory_exporter import (
    InMemoryMetricsExporter,
    sanitize_metric_attributes,
)
from nexusai.infrastructure.observability.structured_logging_exporter import StructuredLoggingExporter


@pytest.mark.asyncio
async def test_in_memory_exporter_metrics_and_events() -> None:
    """Test InMemoryMetricsExporter counters, gauges, durations, events, snapshot, and reset."""
    exporter = InMemoryMetricsExporter()

    await exporter.increment_counter("nexusai_executions_total", 1, attributes={"tool_name": "search"})
    await exporter.record_gauge("nexusai_scheduler_queue_depth", 4.0)
    await exporter.record_duration("nexusai_execution_duration_ms", 120.5)

    evt = RuntimeEvent(
        event_id="evt-1",
        event_type=RuntimeEventType.EXECUTION_STARTED,
        execution_id="exec-1",
    )
    await exporter.emit_event(evt)

    snap = exporter.snapshot()

    assert snap.counters["nexusai_executions_total"] == 1
    assert snap.gauges["nexusai_scheduler_queue_depth"] == 4.0
    assert snap.duration_samples["nexusai_execution_duration_ms"] == [120.5]
    assert len(snap.events) == 1
    assert snap.events[0].execution_id == "exec-1"

    exporter.reset()
    snap_after = exporter.snapshot()
    assert len(snap_after.counters) == 0
    assert len(snap_after.events) == 0


def test_cardinality_governance_attribute_filtering() -> None:
    """Test Cardinality Policy: High cardinality dimensions (execution_id, node_id, task_id) are omitted from metric labels."""
    attrs = {
        "tool_name": "execute_terminal",
        "execution_id": "exec-high-cardinality-uuid-12345",
        "node_id": "node-99",
        "task_id": "task-99",
        "status": "COMPLETED",
    }

    clean = sanitize_metric_attributes(attrs)

    assert "tool_name" in clean
    assert "status" in clean
    assert "execution_id" not in clean, "High cardinality execution_id must be excluded from metric labels"
    assert "node_id" not in clean, "High cardinality node_id must be excluded from metric labels"
    assert "task_id" not in clean, "High cardinality task_id must be excluded from metric labels"


@pytest.mark.asyncio
async def test_exporter_fault_isolation_invariant() -> None:
    """Test Fault Isolation Invariant: Telemetry exporter crashes NEVER raise exceptions to caller."""
    faulty_exporter = InMemoryMetricsExporter(fail_on_purpose=True)

    # All calls should complete without raising exceptions
    await faulty_exporter.increment_counter("test_counter")
    await faulty_exporter.record_gauge("test_gauge", 10.0)
    await faulty_exporter.record_duration("test_duration", 5.0)
    await faulty_exporter.emit_event(
        RuntimeEvent(event_id="e1", event_type=RuntimeEventType.EXECUTION_STARTED)
    )


@pytest.mark.asyncio
async def test_structured_logging_exporter_json_stream() -> None:
    """Test StructuredLoggingExporter outputs valid JSON records with secret redaction to stream."""
    stream = io.StringIO()
    exporter = StructuredLoggingExporter(stream=stream)

    evt = RuntimeEvent(
        event_id="evt-json-1",
        event_type=RuntimeEventType.TOOL_STARTED,
        execution_id="exec-j1",
        attributes={"tool_name": "search", "api_key": "secret-token"},
    )
    await exporter.emit_event(evt)

    output_line = stream.getvalue().strip()
    assert output_line.startswith("{") and output_line.endswith("}")

    data = json.loads(output_line)
    assert data["event_type"] == "TOOL_STARTED"
    assert data["execution_id"] == "exec-j1"
    assert data["attributes"]["api_key"] == "[REDACTED_SECRET]"


if __name__ == "__main__":
    asyncio.run(test_in_memory_exporter_metrics_and_events())
    test_cardinality_governance_attribute_filtering()
    asyncio.run(test_exporter_fault_isolation_invariant())
    asyncio.run(test_structured_logging_exporter_json_stream())
    print("ALL P2-4 METRICS EXPORTER UNIT TESTS PASSED SUCCESSFULLY!")
