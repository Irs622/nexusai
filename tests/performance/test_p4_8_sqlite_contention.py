"""P4-8-C SQLite and WAL Contention Stress Test suite."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import time
import pytest

from nexusai.brain.domain.audit import AuditEvent, AuditEventType
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore
from tests.performance.metrics import PerformanceMetrics


@pytest.mark.asyncio
async def test_sqlite_wal_contention_stress() -> None:
    """Stress Test: 30 concurrent writer connections to SQLite WAL mode store measuring lock contention and transaction latency."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        metrics = PerformanceMetrics(benchmark_name="P4-8-C SQLite WAL Contention", workers=30)

        async def connection_worker(w_idx: int) -> None:
            store = SQLiteAuditStore(db_path=db_path)
            for i in range(10):
                t0 = time.perf_counter()
                try:
                    ev = AuditEvent(
                        event_id=f"evt-cont-{w_idx}-{i}",
                        event_type=AuditEventType.TOOL_EXECUTION_COMPLETED.value,
                        session_id=f"sess-cont-{w_idx}",
                        execution_id=f"exec-cont-{w_idx}",
                        plan_fingerprint="fp-cont-1",
                        sequence_number=0,
                    )
                    await store.append_event(ev)
                    t1 = time.perf_counter()
                    metrics.record_operation((t1 - t0) * 1000.0, success=True)
                except sqlite3.OperationalError as err:
                    t1 = time.perf_counter()
                    metrics.sqlite_contention_count += 1
                    metrics.record_operation((t1 - t0) * 1000.0, success=False)

        workers = [asyncio.create_task(connection_worker(i)) for i in range(30)]
        await asyncio.gather(*workers)

        metrics.finalize()
        metrics.export_json()

        d = metrics.to_dict()
        print(f"\n[P4-8-C SQLITE WAL CONTENTION RESULTS]")
        print(f"Total Operations: {d['total_operations']} | Contention Count: {d['sqlite_contention_count']}")
        print(f"Latencies (ms) -> p50: {d['latency_ms']['p50']} | p95: {d['latency_ms']['p95']} | p99: {d['latency_ms']['p99']} | max: {d['latency_ms']['max']}")

        assert d["total_operations"] == 300
        assert d["successful_operations"] == 300, "All 300 transactions MUST complete under WAL busy timeout!"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_sqlite_wal_contention_stress())
    print("ALL P4-8-C SQLITE CONTENTION STRESS TESTS PASSED SUCCESSFULLY!")
