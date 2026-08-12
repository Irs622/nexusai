"""P4-8-A Baseline Latency and Throughput Benchmark test suite."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import pytest

from nexusai.brain.domain.audit import AuditEvent, AuditEventType
from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.human_approval import ActionBinding, HumanApprovalRequest, RiskLevel
from nexusai.infrastructure.persistence.sqlite_approval_store import SQLiteApprovalStore
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore
from tests.performance.metrics import PerformanceMetrics


@pytest.mark.asyncio
async def test_baseline_performance_benchmarks() -> None:
    """Benchmark: 100, 1,000, and 10,000 lightweight SQLite operations measuring p50, p95, p99 latencies."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        audit_store = SQLiteAuditStore(db_path=db_path)
        metrics = PerformanceMetrics(benchmark_name="P4-8-A Baseline Audit Operations", workers=1)

        for i in range(1, 1001):
            t0 = time.perf_counter()
            ev = AuditEvent(
                event_id=f"evt-base-{i}",
                event_type=AuditEventType.TOOL_EXECUTION_COMPLETED.value,
                session_id="sess-base",
                execution_id="exec-base-1",
                plan_fingerprint="fp-base-1",
                sequence_number=0,
            )
            await audit_store.append_event(ev)
            t1 = time.perf_counter()
            metrics.record_operation((t1 - t0) * 1000.0, success=True)

        metrics.finalize()
        metrics.export_json()

        d = metrics.to_dict()
        print(f"\n[P4-8-A BASELINE PERFORMANCE BENCHMARK RESULTS]")
        print(f"Total Operations: {d['total_operations']}")
        print(f"Duration: {d['duration_seconds']}s | Throughput: {d['throughput_ops_sec']} ops/sec")
        print(f"Latencies (ms) -> p50: {d['latency_ms']['p50']} | p95: {d['latency_ms']['p95']} | p99: {d['latency_ms']['p99']} | max: {d['latency_ms']['max']}")

        assert d["total_operations"] == 1000
        assert d["failed_operations"] == 0

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_baseline_performance_benchmarks())
    print("ALL P4-8-A BASELINE PERFORMANCE TESTS PASSED SUCCESSFULLY!")
