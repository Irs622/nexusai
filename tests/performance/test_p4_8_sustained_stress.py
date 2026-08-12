"""P4-8-G Sustained Stress Test suite across 50 concurrent workers."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import pytest

from nexusai.brain.domain.execution_coordination import WorkerIdentity
from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.domain.human_approval import ActionBinding, ApprovalStatus, HumanApprovalDecision, HumanApprovalRequest, RiskLevel
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine
from nexusai.infrastructure.persistence.sqlite_approval_store import SQLiteApprovalStore
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import SQLiteExecutionCoordinator
from tests.performance.metrics import PerformanceMetrics


@pytest.mark.asyncio
async def test_sustained_stress_workload_50_workers() -> None:
    """Sustained Stress Test: 50 workers executing mixed lifecycle operations continuously."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        coord = SQLiteExecutionCoordinator(db_path=db_path)
        approval_store = SQLiteApprovalStore(db_path=db_path)
        approval_engine = HumanApprovalEngine(store=approval_store)
        gov = GovernanceEngine(global_budget=ResourceBudget(max_concurrent_tasks=100, max_tool_invocations=200))
        metrics = PerformanceMetrics(benchmark_name="P4-8-G Sustained Stress 50 Workers", workers=50)

        async def worker_loop(w_idx: int) -> None:
            w = WorkerIdentity(f"worker-stress-{w_idx}")
            for i in range(5):
                exec_id = f"exec-sus-{w_idx}-{i}"
                sess_id = f"sess-sus-{w_idx}"

                t0 = time.perf_counter()
                lease = await coord.acquire_execution_lease(exec_id, sess_id, w)

                binding = ActionBinding(
                    session_id=sess_id,
                    execution_id=exec_id,
                    plan_fingerprint=f"fp-sus-{w_idx}-{i}",
                    node_id="n1",
                    tool_id="process_tool",
                    tool_version="1.0.0",
                    requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
                )
                req = HumanApprovalRequest(f"app-sus-{w_idx}-{i}", binding, RiskLevel.HIGH, "Run process")
                await approval_engine.request_approval(req)

                dec = HumanApprovalDecision(f"app-sus-{w_idx}-{i}", ApprovalStatus.APPROVED, "op@co.com", "Approved")
                grant = await approval_engine.submit_decision(dec)
                await approval_engine.verify_and_consume_grant(grant.grant_id, binding)

                res = await gov.authorize(exec_id, frozenset({ToolCapability.PROCESS_EXEC}))
                t1 = time.perf_counter()

                metrics.record_operation((t1 - t0) * 1000.0, success=res.allowed)

                if res.allowed:
                    await gov.release(res.reservation_id)
                await coord.release_execution_lease(lease.lease_id, w)

        workers = [asyncio.create_task(worker_loop(w)) for w in range(50)]
        await asyncio.gather(*workers)

        metrics.finalize()
        metrics.export_json()

        d = metrics.to_dict()
        print(f"\n[P4-8-G SUSTAINED STRESS TEST RESULTS]")
        print(f"Total Operations: {d['total_operations']} | Throughput: {d['throughput_ops_sec']} ops/sec")
        print(f"Latencies (ms) -> p50: {d['latency_ms']['p50']} | p95: {d['latency_ms']['p95']} | p99: {d['latency_ms']['p99']} | max: {d['latency_ms']['max']}")

        assert d["successful_operations"] == 250
        assert d["failed_operations"] == 0
        assert gov.get_active_reservation_count() == 0, "Zero leaked governance reservations invariant MUST hold!"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_sustained_stress_workload_50_workers())
    print("ALL P4-8-G SUSTAINED STRESS TESTS PASSED SUCCESSFULLY!")
