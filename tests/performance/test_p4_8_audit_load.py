"""P4-8-E Audit Scalability and Verification Load Test suite (1,000 and 10,000 event chains)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import pytest

from nexusai.brain.domain.audit import AuditEvent, AuditEventType
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore
from tests.performance.metrics import PerformanceMetrics


@pytest.mark.asyncio
async def test_audit_load_10k_event_scaling() -> None:
    """Load Test: 10,000 sequential audit events append and full tamper-evident chain verification scaling."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteAuditStore(db_path=db_path)
        metrics = PerformanceMetrics(benchmark_name="P4-8-E Audit 10k Scaling Load", workers=1)

        t_append_start = time.perf_counter()
        for i in range(1, 10001):
            t0 = time.perf_counter()
            ev = AuditEvent(
                event_id=f"evt-10k-{i}",
                event_type=AuditEventType.TOOL_EXECUTION_COMPLETED.value,
                session_id="sess-10k",
                execution_id="exec-10k-1",
                plan_fingerprint="fp-10k-1",
                sequence_number=0,
            )
            await store.append_event(ev)
            t1 = time.perf_counter()
            metrics.record_operation((t1 - t0) * 1000.0, success=True)

        metrics.finalize()

        # Measure 10,000 Event Verification Latency
        t_v0 = time.perf_counter()
        res = await store.verify_chain("exec-10k-1")
        t_v1 = time.perf_counter()
        verify_ms = (t_v1 - t_v0) * 1000.0

        metrics.export_json()
        d = metrics.to_dict()

        print(f"\n[P4-8-E AUDIT 10,000 EVENT SCALING RESULTS]")
        print(f"Append Total Events: {d['total_operations']} | Append Throughput: {d['throughput_ops_sec']} ops/sec")
        print(f"Append Latencies (ms) -> p50: {d['latency_ms']['p50']} | p95: {d['latency_ms']['p95']} | p99: {d['latency_ms']['p99']} | max: {d['latency_ms']['max']}")
        print(f"10,000 Event Chain Verification Latency: {verify_ms:.2f} ms")

        assert res.valid is True
        assert res.event_count == 10000

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_audit_load_10k_event_scaling())
    print("ALL P4-8-E AUDIT SCALABILITY LOAD TESTS PASSED SUCCESSFULLY!")
