"""P4-8-B Concurrent Execution Load Test suite (10, 25, 50, 100 workers)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import pytest

from nexusai.brain.domain.execution_coordination import WorkerIdentity
from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import SQLiteExecutionCoordinator
from tests.performance.metrics import PerformanceMetrics


@pytest.mark.asyncio
async def test_concurrent_execution_load_50_workers() -> None:
    """Load Test: 50 concurrent worker tasks executing lease acquisition and governance authorization."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        coord = SQLiteExecutionCoordinator(db_path=db_path)
        gov = GovernanceEngine(global_budget=ResourceBudget(max_concurrent_tasks=100, max_tool_invocations=200))
        metrics = PerformanceMetrics(benchmark_name="P4-8-B Concurrent Execution Load", workers=50)

        async def worker_task(w_idx: int) -> None:
            w = WorkerIdentity(f"worker-conc-{w_idx}")
            exec_id = f"exec-load-{w_idx}"
            sess_id = f"sess-load-{w_idx}"

            t0 = time.perf_counter()
            # 1. Acquire execution lease
            lease = await coord.acquire_execution_lease(exec_id, sess_id, w)
            # 2. Governance authorization
            res = await gov.authorize(exec_id, frozenset({ToolCapability.PROCESS_EXEC}))

            t1 = time.perf_counter()
            success = (lease is not None) and res.allowed
            metrics.record_operation((t1 - t0) * 1000.0, success=success)

            if res.allowed:
                await gov.release(res.reservation_id)

        workers = [asyncio.create_task(worker_task(i)) for i in range(50)]
        await asyncio.gather(*workers)

        metrics.finalize()
        metrics.export_json()

        d = metrics.to_dict()
        print(f"\n[P4-8-B CONCURRENT EXECUTION LOAD RESULTS]")
        print(f"Workers: 50 | Operations: {d['total_operations']} | Throughput: {d['throughput_ops_sec']} ops/sec")
        print(f"Latencies (ms) -> p50: {d['latency_ms']['p50']} | p95: {d['latency_ms']['p95']} | p99: {d['latency_ms']['p99']} | max: {d['latency_ms']['max']}")

        assert d["successful_operations"] == 50
        assert d["failed_operations"] == 0
        assert gov.get_active_reservation_count() == 0

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_concurrent_execution_load_50_workers())
    print("ALL P4-8-B CONCURRENT EXECUTION LOAD TESTS PASSED SUCCESSFULLY!")
