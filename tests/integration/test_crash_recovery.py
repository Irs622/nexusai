"""Integration test suite for Durable Execution Engine Crash Recovery, Checkpointing, and Fencing Tokens."""

from __future__ import annotations

import asyncio
import tempfile
from typing import Any

import pytest

from nexusai.brain.domain.execution_coordination import WorkerIdentity
from nexusai.brain.domain.execution_state import ExecutionStatus, NodeExecutionStatus
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore
from nexusai.infrastructure.persistence.sqlite_execution_coordinator import (
    SQLiteExecutionCoordinator,
)
from nexusai.infrastructure.persistence.sqlite_execution_store import SQLiteExecutionStateStore
from nexusai.runtime.execution_engine import (
    ApprovalRequiredError,
    DurableExecutionEngine,
    DurableExecutionState,
)
from nexusai.runtime.execution_semantics import ExecutionSemantics
from nexusai.runtime.recovery import CrashRecoveryProtocol
from nexusai.runtime.retry_policy import DurableRetryPolicy
from nexusai.security.guard import RiskLevel


@pytest.mark.asyncio
async def test_multistep_dag_crash_and_resume_from_checkpoint() -> None:
    """Test Multi-step DAG: 3/5 steps complete -> crash simulated -> restart -> only steps 4-5 execute."""
    with (
        tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf_exec,
        tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf_coord,
        tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf_audit,
    ):
        exec_db = tf_exec.name
        coord_db = tf_coord.name
        audit_db = tf_audit.name

    store = SQLiteExecutionStateStore(db_path=exec_db)
    coord = SQLiteExecutionCoordinator(db_path=coord_db)
    audit = SQLiteAuditStore(db_path=audit_db)
    worker_1 = WorkerIdentity(worker_id="worker-01")

    engine_1 = DurableExecutionEngine(
        store=store, coordinator=coord, audit_store=audit, worker_identity=worker_1
    )

    exec_id = "exec-dag-5steps"
    nodes = [
        {"id": "1", "tool": "step_1_tool"},
        {"id": "2", "tool": "step_2_tool"},
        {"id": "3", "tool": "step_3_tool"},
        {"id": "4", "tool": "step_4_tool"},
        {"id": "5", "tool": "step_5_tool"},
    ]

    executed_step_ids: list[str] = []

    async def simulated_executor(node: dict[str, Any], attempt: int) -> dict[str, Any]:
        nid = str(node["id"])
        executed_step_ids.append(nid)
        if nid == "3":
            # Simulate hard process crash right after step 3 finishes and checkpoints
            pass
        return {"step": nid, "output": f"data_{nid}"}

    # First run: we simulate a crash after step 3 completes
    # We execute steps 1, 2, 3 and then interrupt
    try:

        async def crashing_executor(node: dict[str, Any], attempt: int) -> dict[str, Any]:
            nid = str(node["id"])
            executed_step_ids.append(nid)
            if nid == "4":
                raise KeyboardInterrupt("Simulated sudden worker process SIGKILL")
            return {"step": nid, "output": f"data_{nid}"}

        await engine_1.execute_dag(
            execution_id=exec_id,
            plan_id="plan-crash-test",
            nodes=nodes,
            step_executor=crashing_executor,
            lease_ttl_seconds=0.2,
        )
    except KeyboardInterrupt:
        pass  # Process crashed

    # Verify steps 1, 2, 3 were executed and checkpointed
    assert "1" in executed_step_ids
    assert "2" in executed_step_ids
    assert "3" in executed_step_ids
    assert "4" in executed_step_ids

    rec_crashed = await store.load_execution(exec_id)
    assert rec_crashed is not None
    assert (
        rec_crashed.node_records.get("1") or rec_crashed.node_records.get(1)
    ).status == NodeExecutionStatus.COMPLETED
    assert (
        rec_crashed.node_records.get("2") or rec_crashed.node_records.get(2)
    ).status == NodeExecutionStatus.COMPLETED
    assert (
        rec_crashed.node_records.get("3") or rec_crashed.node_records.get(3)
    ).status == NodeExecutionStatus.COMPLETED

    # Step 4 crashed before completion
    step_4_rec = rec_crashed.node_records.get("4") or rec_crashed.node_records.get(4)
    assert step_4_rec.status != NodeExecutionStatus.COMPLETED

    # Let lease expire
    await asyncio.sleep(0.3)

    # 2. Worker 2 starts up and resumes execution
    worker_2 = WorkerIdentity(worker_id="worker-02")
    engine_2 = DurableExecutionEngine(
        store=store, coordinator=coord, audit_store=audit, worker_identity=worker_2
    )

    resumed_step_ids: list[str] = []

    async def resume_executor(node: dict[str, Any], attempt: int) -> dict[str, Any]:
        nid = str(node["id"])
        resumed_step_ids.append(nid)
        return {"step": nid, "output": f"resumed_{nid}"}

    res = await engine_2.resume_execution(
        execution_id=exec_id,
        nodes=nodes,
        step_executor=resume_executor,
        actor="worker-02",
    )

    assert res["status"] == DurableExecutionState.SUCCEEDED.value
    # Acceptance Criteria: Steps 1, 2, 3 were already completed -> on resume, ONLY steps 4 and 5 execute!
    assert "1" not in resumed_step_ids
    assert "2" not in resumed_step_ids
    assert "3" not in resumed_step_ids
    assert "4" in resumed_step_ids
    assert "5" in resumed_step_ids

    # Verify final state is SUCCEEDED in durable SQLite store
    rec_final = await store.load_execution(exec_id)
    assert rec_final is not None
    assert rec_final.status == ExecutionStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_crash_recovery_protocol_expired_lease_reclaim() -> None:
    """Test CrashRecoveryProtocol reclaims expired lease with higher fencing token on startup."""
    store = SQLiteExecutionStateStore(db_path=":memory:")
    coord = SQLiteExecutionCoordinator(db_path=":memory:")
    audit = SQLiteAuditStore(db_path=":memory:")

    worker_dead = WorkerIdentity(worker_id="worker-crashed")
    worker_recovery = WorkerIdentity(worker_id="worker-recovery")

    engine = DurableExecutionEngine(
        store=store, coordinator=coord, audit_store=audit, worker_identity=worker_dead
    )
    exec_id = "exec-stale-01"

    # Worker dead acquires lease (fencing_token = 1) with 0.1s TTL
    lease = await coord.acquire_execution_lease(exec_id, "plan-1", worker_dead, ttl_seconds=0.1)
    assert lease.fencing_token == 1

    # Record execution as RUNNING in store
    from nexusai.brain.domain.execution_state import ExecutionRecord

    rec = ExecutionRecord(
        execution_id=exec_id,
        plan_id="plan-1",
        graph_hash="hash-1",
        status=ExecutionStatus.RUNNING,
        fencing_token=1,
        worker_id="worker-crashed",
    )
    await store.create_execution(rec)

    # Lease expires
    await asyncio.sleep(0.2)

    # Run CrashRecoveryProtocol with worker_recovery
    recovery = CrashRecoveryProtocol(
        store=store,
        coordinator=coord,
        engine=engine,
        worker_identity=worker_recovery,
    )

    report = await recovery.run_startup_recovery()
    assert report.total_scanned >= 1
    assert report.reclaimed_count == 1
    assert exec_id in report.recovered_execution_ids

    # Check that new lease has higher fencing token
    new_lease = await coord.get_current_lease(exec_id)
    assert new_lease is not None
    assert new_lease.fencing_token == 2
    assert new_lease.worker_id == "worker-recovery"

    # Check store state transitioned to FAILED_RETRYABLE with fencing_token 2
    loaded = await store.load_execution(exec_id)
    assert loaded is not None
    assert loaded.status == ExecutionStatus.FAILED_RETRYABLE
    assert loaded.fencing_token == 2


@pytest.mark.asyncio
async def test_cancelled_execution_does_not_resume_on_restart() -> None:
    """Test that an execution marked CANCELLED survives restart and is not resumed by recovery protocol."""
    store = SQLiteExecutionStateStore(db_path=":memory:")
    coord = SQLiteExecutionCoordinator(db_path=":memory:")
    audit = SQLiteAuditStore(db_path=":memory:")

    worker = WorkerIdentity(worker_id="worker-01")
    engine = DurableExecutionEngine(
        store=store, coordinator=coord, audit_store=audit, worker_identity=worker
    )
    exec_id = "exec-cancelled-no-resume"

    from nexusai.brain.domain.execution_state import ExecutionRecord

    rec = ExecutionRecord(
        execution_id=exec_id,
        plan_id="plan-1",
        graph_hash="hash-1",
        status=ExecutionStatus.RUNNING,
    )
    await store.create_execution(rec)

    # Simulate an execution that had cancellation requested right as the process crashed
    await store.mark_cancellation_requested(exec_id)

    # Run CrashRecoveryProtocol on startup
    recovery = CrashRecoveryProtocol(
        store=store, coordinator=coord, engine=engine, worker_identity=worker
    )
    report = await recovery.run_startup_recovery()

    # Cancelled execution is finalized as CANCELLED and never resumed
    assert report.cancelled_count == 1
    assert exec_id not in report.recovered_execution_ids

    loaded = await store.load_execution(exec_id)
    assert loaded is not None
    assert loaded.status == ExecutionStatus.CANCELLED

    # Verify that engine.resume_execution refuses to execute cancelled execution
    resume_res = await engine.resume_execution(
        execution_id=exec_id,
        nodes=[{"id": "1", "tool": "test"}],
        step_executor=lambda n, a: asyncio.sleep(0.01),
    )
    assert resume_res["status"] == DurableExecutionState.CANCELLED.value
    assert resume_res["resumed"] is False


@pytest.mark.asyncio
async def test_at_least_once_retry_warning_and_approval_gate() -> None:
    """Test that at_least_once tool retry requires approval for HIGH risk and succeeds when approved."""
    store = SQLiteExecutionStateStore(db_path=":memory:")
    coord = SQLiteExecutionCoordinator(db_path=":memory:")
    audit = SQLiteAuditStore(db_path=":memory:")
    worker = WorkerIdentity(worker_id="worker-01")

    engine = DurableExecutionEngine(
        store=store, coordinator=coord, audit_store=audit, worker_identity=worker
    )

    attempts = 0

    async def flaky_high_risk(node: dict[str, Any], attempt: int) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise RuntimeError("Transient TIMEOUT connecting to external payment service")
        return {"payment_id": "pay-12345"}

    policy = DurableRetryPolicy(max_attempts=3, base_delay_seconds=0.01, jitter=False)

    # Case A: retry_approval_granted = False -> raises ApprovalRequiredError
    node_unapproved = [
        {
            "id": "1",
            "tool": "charge_credit_card",
            "execution_semantics": ExecutionSemantics.AT_LEAST_ONCE,
            "risk_level": RiskLevel.HIGH,
            "retry_approval_granted": False,
        }
    ]

    with pytest.raises(ApprovalRequiredError):
        await engine.execute_dag(
            execution_id="exec-unapproved",
            plan_id="plan-pay",
            nodes=node_unapproved,
            step_executor=flaky_high_risk,
            retry_policy=policy,
        )

    # Case B: retry_approval_granted = True -> retry proceeds and succeeds
    attempts = 0
    node_approved = [
        {
            "id": "1",
            "tool": "charge_credit_card",
            "execution_semantics": ExecutionSemantics.AT_LEAST_ONCE,
            "risk_level": RiskLevel.HIGH,
            "retry_approval_granted": True,
        }
    ]

    res = await engine.execute_dag(
        execution_id="exec-approved",
        plan_id="plan-pay",
        nodes=node_approved,
        step_executor=flaky_high_risk,
        retry_policy=policy,
    )
    assert res["status"] == DurableExecutionState.SUCCEEDED.value
    assert attempts == 2
