"""Empirical audit performance benchmark test suite for P4-7."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import pytest

from nexusai.brain.domain.audit import AuditEvent, AuditEventType
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore


@pytest.mark.asyncio
async def test_audit_performance_benchmarks() -> None:
    """Benchmark: 1,000 sequential events append & tamper-evident chain verification."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteAuditStore(db_path=db_path)

        # 1. Benchmark 1,000 Sequential Appends
        t_start = time.perf_counter()
        for i in range(1, 1001):
            ev = AuditEvent(
                event_id=f"evt-perf-{i}",
                event_type=AuditEventType.TOOL_EXECUTION_COMPLETED.value,
                session_id="sess-perf-1",
                execution_id="exec-perf-1",
                plan_fingerprint="fp-perf-1",
                sequence_number=0,
            )
            await store.append_event(ev)
        t_append_end = time.perf_counter()
        append_duration_ms = (t_append_end - t_start) * 1000.0

        # 2. Benchmark 1,000 Event Hash Chain Verification
        v_start = time.perf_counter()
        res = await store.verify_chain("exec-perf-1")
        v_end = time.perf_counter()
        verify_duration_ms = (v_end - v_start) * 1000.0

        assert res.valid is True
        assert res.event_count == 1000

        print(f"\n[P4-7 EMPIRICAL AUDIT PERFORMANCE RESULTS]")
        print(f"1,000 Sequential Event Appends: {append_duration_ms:.2f} ms ({append_duration_ms/1000.0:.3f} ms/event)")
        print(f"1,000 Event Chain Verification: {verify_duration_ms:.2f} ms")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_audit_performance_benchmarks())
    print("ALL AUDIT PERFORMANCE BENCHMARK TESTS PASSED SUCCESSFULLY!")
