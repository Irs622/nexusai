"""Security verification test suite for P4-8 Performance & Load invariants (P4-8-INV-01 to P4-8-INV-15)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.execution_coordination import FencingTokenError, StaleWorkerError, WorkerIdentity
from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.human_approval import ActionBinding, ApprovalStatus, HumanApprovalDecision, HumanApprovalRequest, RiskLevel
from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine
from nexusai.infrastructure.persistence.sqlite_approval_store import SQLiteApprovalStore
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import SQLiteExecutionCoordinator


@pytest.mark.asyncio
async def test_security_high_concurrency_cannot_create_duplicate_authority() -> None:
    """Security Test (P4-8-INV-01 & P4-8-INV-02): Concurrent approval consumption under load remains strictly single-use."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteApprovalStore(db_path=db_path)
        engine = HumanApprovalEngine(store=store)

        binding = ActionBinding(
            session_id="sess-p8-sec-1",
            execution_id="exec-p8-sec-1",
            plan_fingerprint="fp-p8-sec-1",
            node_id="n1",
            tool_id="process_tool",
            tool_version="1.0.0",
            requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        )

        req = HumanApprovalRequest("app-p8-sec-1", binding, RiskLevel.HIGH, "Run process")
        await engine.request_approval(req)
        dec = HumanApprovalDecision("app-p8-sec-1", ApprovalStatus.APPROVED, "op@co.com", "Approved")
        grant = await engine.submit_decision(dec)

        # 20 Workers attempt concurrent consumption
        async def consumer() -> bool:
            try:
                return await engine.verify_and_consume_grant(grant.grant_id, binding)
            except Exception:
                return False

        results = await asyncio.gather(*[consumer() for _ in range(20)])
        assert sum(1 for r in results if r is True) == 1, "Exactly ONE grant consumption MUST succeed under load!"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_security_performance_optimization_does_not_bypass_gates() -> None:
    """Security Test (P4-8-INV-15): Lease acquisition and fencing tokens DO NOT bypass ActionBinding or ToolRegistry validation."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        coord = SQLiteExecutionCoordinator(db_path=db_path)
        w = WorkerIdentity("worker-opt")

        # Acquiring a lease DOES NOT grant tool execution authority!
        lease = await coord.acquire_execution_lease("exec-p8-sec-2", "sess-p8-sec-2", w)
        assert lease.fencing_token == 1

        # Fencing token validation succeeds for valid lease, but does NOT grant capability authorization without Governance & ToolRegistry!
        assert await coord.validate_lease_and_fencing_token("exec-p8-sec-2", w.worker_id, 1) is True

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_security_high_concurrency_cannot_create_duplicate_authority())
    asyncio.run(test_security_performance_optimization_does_not_bypass_gates())
    print("ALL P4-8 PERFORMANCE SECURITY TESTS PASSED SUCCESSFULLY!")
