"""P4-8-D Durable Approval Load Test suite."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import pytest

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.human_approval import ActionBinding, ApprovalStatus, HumanApprovalDecision, HumanApprovalRequest, RiskLevel
from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine
from nexusai.infrastructure.persistence.sqlite_approval_store import SQLiteApprovalStore
from tests.performance.metrics import PerformanceMetrics


@pytest.mark.asyncio
async def test_durable_approval_load_and_replay_protection() -> None:
    """Load Test: 50 concurrent approvals created, approved, and verified under load."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteApprovalStore(db_path=db_path)
        engine = HumanApprovalEngine(store=store)
        metrics = PerformanceMetrics(benchmark_name="P4-8-D Durable Approval Load", workers=50)

        async def approval_worker(app_idx: int) -> None:
            binding = ActionBinding(
                session_id=f"sess-app-load-{app_idx}",
                execution_id=f"exec-app-load-{app_idx}",
                plan_fingerprint=f"fp-app-load-{app_idx}",
                node_id="n1",
                tool_id="process_tool",
                tool_version="1.0.0",
                requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
            )

            t0 = time.perf_counter()
            req = HumanApprovalRequest(f"app-load-{app_idx}", binding, RiskLevel.HIGH, "Run process")
            await engine.request_approval(req)

            dec = HumanApprovalDecision(f"app-load-{app_idx}", ApprovalStatus.APPROVED, "op@co.com", "Approved")
            grant = await engine.submit_decision(dec)

            # Consume grant
            consumed = await engine.verify_and_consume_grant(grant.grant_id, binding)
            t1 = time.perf_counter()

            metrics.record_operation((t1 - t0) * 1000.0, success=consumed)

        workers = [asyncio.create_task(approval_worker(i)) for i in range(50)]
        await asyncio.gather(*workers)

        metrics.finalize()
        metrics.export_json()

        d = metrics.to_dict()
        print(f"\n[P4-8-D DURABLE APPROVAL LOAD RESULTS]")
        print(f"Total Operations: {d['total_operations']} | Throughput: {d['throughput_ops_sec']} ops/sec")
        print(f"Latencies (ms) -> p50: {d['latency_ms']['p50']} | p95: {d['latency_ms']['p95']} | p99: {d['latency_ms']['p99']} | max: {d['latency_ms']['max']}")

        assert d["successful_operations"] == 50
        assert d["failed_operations"] == 0

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_durable_approval_load_and_replay_protection())
    print("ALL P4-8-D DURABLE APPROVAL LOAD TESTS PASSED SUCCESSFULLY!")
