"""Unit tests for DurableExecutionEngine, State Machine, Fencing Tokens, and Retry Semantics."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from nexusai.brain.domain.execution_coordination import FencingTokenError, WorkerIdentity
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
    InvalidStateTransitionError,
)
from nexusai.runtime.execution_semantics import ExecutionSemantics
from nexusai.runtime.retry_policy import DurableRetryPolicy
from nexusai.security.guard import RiskLevel


@pytest.fixture
def temp_durable_setup() -> tuple[
    SQLiteExecutionStateStore,
    SQLiteExecutionCoordinator,
    SQLiteAuditStore,
    DurableExecutionEngine,
]:
    """Provide a fresh isolated SQLite-backed durable execution environment."""
    store = SQLiteExecutionStateStore(db_path=":memory:")
    coordinator = SQLiteExecutionCoordinator(db_path=":memory:")
    audit_store = SQLiteAuditStore(db_path=":memory:")
    worker = WorkerIdentity(worker_id="test-worker-01")
    engine = DurableExecutionEngine(
        store=store,
        coordinator=coordinator,
        audit_store=audit_store,
        worker_identity=worker,
    )
    return store, coordinator, audit_store, engine


@pytest.mark.asyncio
async def test_state_machine_valid_transitions(
    temp_durable_setup: tuple[
        SQLiteExecutionStateStore,
        SQLiteExecutionCoordinator,
        SQLiteAuditStore,
        DurableExecutionEngine,
    ],
) -> None:
    """Test standard sequential valid state machine transitions: CREATED -> QUEUED -> RUNNING -> CHECKPOINT -> SUCCEEDED."""
    store, coord, audit_store, engine = temp_durable_setup
    exec_id = "exec-test-sm-1"

    # Initialize execution in store
    await engine.execute_dag(
        execution_id=exec_id,
        plan_id="plan-1",
        nodes=[{"id": "1", "tool": "test_tool"}],
        step_executor=lambda n, att: asyncio.sleep(0.01, result={"ok": True}),
    )

    history = await store.get_state_history(exec_id)
    states = [h["to_state"] for h in history]
    assert "QUEUED" in states
    assert "RUNNING" in states
    assert "CHECKPOINT" in states
    assert "SUCCEEDED" in states

    rec = await store.load_execution(exec_id)
    assert rec is not None
    assert rec.status == ExecutionStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_state_machine_invalid_transition(
    temp_durable_setup: tuple[
        SQLiteExecutionStateStore,
        SQLiteExecutionCoordinator,
        SQLiteAuditStore,
        DurableExecutionEngine,
    ],
) -> None:
    """Test that illegal transition (e.g. CREATED -> SUCCEEDED directly) raises InvalidStateTransitionError."""
    store, coord, audit_store, engine = temp_durable_setup
    exec_id = "exec-invalid-sm"

    # Create directly in CREATED
    from nexusai.brain.domain.execution_state import ExecutionRecord

    rec = ExecutionRecord(
        execution_id=exec_id,
        plan_id="plan-1",
        graph_hash="hash-1",
        status=ExecutionStatus.CREATED,
    )
    await store.create_execution(rec)

    with pytest.raises(InvalidStateTransitionError):
        await engine._transition_state(
            execution_id=exec_id,
            to_state=DurableExecutionState.SUCCEEDED,
            fencing_token=1,
        )


@pytest.mark.asyncio
async def test_state_machine_idempotent_transition(
    temp_durable_setup: tuple[
        SQLiteExecutionStateStore,
        SQLiteExecutionCoordinator,
        SQLiteAuditStore,
        DurableExecutionEngine,
    ],
) -> None:
    """Test that transitioning to the same state twice is a successful no-op."""
    store, coord, audit_store, engine = temp_durable_setup
    exec_id = "exec-idem-sm"

    from nexusai.brain.domain.execution_state import ExecutionRecord

    rec = ExecutionRecord(
        execution_id=exec_id,
        plan_id="plan-1",
        graph_hash="hash-1",
        status=ExecutionStatus.CREATED,
    )
    await store.create_execution(rec)

    # First transition to QUEUED
    res1 = await engine._transition_state(
        execution_id=exec_id,
        to_state=DurableExecutionState.QUEUED,
        fencing_token=1,
    )
    assert res1 is True

    # Second transition to QUEUED (identical)
    res2 = await engine._transition_state(
        execution_id=exec_id,
        to_state=DurableExecutionState.QUEUED,
        fencing_token=1,
    )
    assert res2 is True


@pytest.mark.asyncio
async def test_fencing_token_rejection(
    temp_durable_setup: tuple[
        SQLiteExecutionStateStore,
        SQLiteExecutionCoordinator,
        SQLiteAuditStore,
        DurableExecutionEngine,
    ],
) -> None:
    """Test that a stale worker with an obsolete fencing token is rejected by the store."""
    store, coord, audit_store, engine = temp_durable_setup
    exec_id = "exec-fencing-test"

    worker_a = WorkerIdentity(worker_id="worker-A")
    worker_b = WorkerIdentity(worker_id="worker-B")

    # Worker A acquires lease (fencing_token = 1)
    lease_a = await coord.acquire_execution_lease(exec_id, "plan-1", worker_a, ttl_seconds=0.1)
    assert lease_a.fencing_token == 1

    # Lease expires
    await asyncio.sleep(0.15)

    # Worker B acquires lease (fencing_token = 2)
    lease_b = await coord.recover_expired_execution_lease(exec_id, worker_b, ttl_seconds=30.0)
    assert lease_b.fencing_token == 2

    from nexusai.brain.domain.execution_coordination import CoordinationError, StaleWorkerError

    # Worker A wakes up and attempts validation with stale token 1 -> rejected with StaleWorkerError!
    with pytest.raises((StaleWorkerError, FencingTokenError, CoordinationError)):
        await coord.validate_lease_and_fencing_token(
            exec_id, worker_a.worker_id, lease_a.fencing_token
        )

    # Worker B validation with token 2 -> succeeds!
    is_valid_b = await coord.validate_lease_and_fencing_token(
        exec_id, worker_b.worker_id, lease_b.fencing_token
    )
    assert is_valid_b is True


@pytest.mark.asyncio
async def test_retry_policy_delay_and_classification() -> None:
    """Test DurableRetryPolicy exponential backoff and error classification."""
    policy = DurableRetryPolicy(
        max_attempts=3,
        base_delay_seconds=1.0,
        backoff_factor=2.0,
        jitter=False,
    )

    # Delays
    assert policy.calculate_delay(1) == 1.0
    assert policy.calculate_delay(2) == 2.0
    assert policy.calculate_delay(3) == 4.0

    # Classifications
    assert policy.is_retryable("TIMEOUT occurred on network") is True
    assert policy.is_retryable(TimeoutError("Connection timed out")) is True
    assert policy.is_retryable("PERMISSION_DENIED: User unauthorized") is False
    assert policy.is_retryable(PermissionError("Access denied")) is False
    assert policy.is_retryable("403 Forbidden") is False


@pytest.mark.asyncio
async def test_step_retries_and_checkpointing(
    temp_durable_setup: tuple[
        SQLiteExecutionStateStore,
        SQLiteExecutionCoordinator,
        SQLiteAuditStore,
        DurableExecutionEngine,
    ],
) -> None:
    """Test that transient failures trigger retry with backoff and persist node checkpoints."""
    store, coord, audit_store, engine = temp_durable_setup
    exec_id = "exec-retry-success"

    attempts = 0

    async def flaky_step(node: dict[str, Any], attempt: int) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise RuntimeError("Transient NETWORK_ERROR on socket")
        return {"result": "recovered_data"}

    policy = DurableRetryPolicy(max_attempts=3, base_delay_seconds=0.01, jitter=False)
    nodes = [{"id": "1", "tool": "fetch_api", "execution_semantics": ExecutionSemantics.IDEMPOTENT}]

    res = await engine.execute_dag(
        execution_id=exec_id,
        plan_id="plan-1",
        nodes=nodes,
        step_executor=flaky_step,
        retry_policy=policy,
    )

    assert res["status"] == "SUCCEEDED"
    assert attempts == 2

    rec = await store.load_execution(exec_id)
    assert rec is not None
    node_rec = rec.node_records.get("1") or rec.node_records.get(1)
    assert node_rec is not None
    assert node_rec.status == NodeExecutionStatus.COMPLETED


@pytest.mark.asyncio
async def test_at_least_once_high_risk_requires_approval(
    temp_durable_setup: tuple[
        SQLiteExecutionStateStore,
        SQLiteExecutionCoordinator,
        SQLiteAuditStore,
        DurableExecutionEngine,
    ],
) -> None:
    """Test that an AT_LEAST_ONCE tool with HIGH risk requires approval for retry."""
    store, coord, audit_store, engine = temp_durable_setup
    exec_id = "exec-high-risk-retry"

    async def failing_step(node: dict[str, Any], attempt: int) -> dict[str, Any]:
        raise RuntimeError("Transient TIMEOUT on email server")

    policy = DurableRetryPolicy(max_attempts=3, base_delay_seconds=0.01, jitter=False)
    nodes = [
        {
            "id": "1",
            "tool": "send_email",
            "execution_semantics": ExecutionSemantics.AT_LEAST_ONCE,
            "risk_level": RiskLevel.HIGH,
            "retry_approval_granted": False,
        }
    ]

    with pytest.raises(ApprovalRequiredError):
        await engine.execute_dag(
            execution_id=exec_id,
            plan_id="plan-1",
            nodes=nodes,
            step_executor=failing_step,
            retry_policy=policy,
        )


@pytest.mark.asyncio
async def test_cancellation_marks_durable_state(
    temp_durable_setup: tuple[
        SQLiteExecutionStateStore,
        SQLiteExecutionCoordinator,
        SQLiteAuditStore,
        DurableExecutionEngine,
    ],
) -> None:
    """Test that cancel_execution durably updates store and stops execution."""
    store, coord, audit_store, engine = temp_durable_setup
    exec_id = "exec-cancel-test"

    # Pre-create execution record
    from nexusai.brain.domain.execution_state import ExecutionRecord

    rec = ExecutionRecord(
        execution_id=exec_id,
        plan_id="plan-1",
        graph_hash="hash-1",
        status=ExecutionStatus.RUNNING,
    )
    await store.create_execution(rec)

    # Cancel execution
    cancelled = await engine.cancel_execution(exec_id, reason="User clicked stop")
    assert cancelled is True

    # Verify durable store reflects CANCELLED
    loaded = await store.load_execution(exec_id)
    assert loaded is not None
    assert loaded.status == ExecutionStatus.CANCELLED
    assert await store.is_cancellation_requested(exec_id) is True


@pytest.mark.asyncio
async def test_client_cannot_override_execution_semantics() -> None:
    """Security test: Client cannot send execution_semantics='idempotent' to bypass approval on AT_LEAST_ONCE tools."""
    from pydantic import BaseModel

    from nexusai.tools.base import BaseTool
    from nexusai.tools.registry import ToolRegistry

    class DummyInput(BaseModel):
        pass

    class HighRiskTool(BaseTool):
        name = "high_risk_payout"
        description = "Sends payout"
        risk_level = RiskLevel.HIGH
        execution_semantics = ExecutionSemantics.AT_LEAST_ONCE
        input_schema = DummyInput

        async def execute(self, **kwargs: Any) -> str:
            return "PAID"

    reg = ToolRegistry()
    reg.register(HighRiskTool())

    store = SQLiteExecutionStateStore(db_path=":memory:")
    coord = SQLiteExecutionCoordinator(db_path=":memory:")
    engine = DurableExecutionEngine(
        store=store,
        coordinator=coord,
        worker_identity=WorkerIdentity(worker_id="sec-worker"),
        tool_registry=reg,
    )

    # Malicious client attempts to spoof execution_semantics as "idempotent" in node dictionary
    nodes = [
        {
            "id": 1,
            "tool": "high_risk_payout",
            "execution_semantics": "idempotent",  # Spoofed!
            "risk_level": "LOW",  # Spoofed!
        }
    ]

    attempts = 0

    async def flaky_step(node: dict[str, Any], attempt: int) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise RuntimeError("Transient connection reset")
        return {"status": "ok"}

    # Engine must enforce registry's AT_LEAST_ONCE + HIGH risk, rejecting unapproved retry
    with pytest.raises(ApprovalRequiredError, match="requires explicit human approval"):
        await engine.execute_dag(
            execution_id="exec-sec-spoof",
            plan_id="plan-sec",
            nodes=nodes,
            step_executor=flaky_step,
        )


@pytest.mark.asyncio
async def test_durable_state_journal_logging() -> None:
    """Test that SQLiteExecutionJournal records state transitions when connected to engine."""
    from nexusai.infrastructure.persistence.sqlite_execution_journal import SQLiteExecutionJournal

    store = SQLiteExecutionStateStore(db_path=":memory:")
    coord = SQLiteExecutionCoordinator(db_path=":memory:")
    journal = SQLiteExecutionJournal(db_path=":memory:")
    engine = DurableExecutionEngine(
        store=store,
        coordinator=coord,
        worker_identity=WorkerIdentity(worker_id="journal-worker"),
        journal=journal,
    )

    nodes = [{"id": 1, "tool": "test_tool"}]

    async def step_exec(node: dict[str, Any], attempt: int) -> dict[str, Any]:
        return {"status": "ok"}

    res = await engine.execute_dag(
        execution_id="exec-journal-test",
        plan_id="plan-j",
        nodes=nodes,
        step_executor=step_exec,
    )
    assert res["status"] == "SUCCEEDED"

    history = await journal.get_durable_state_history("exec-journal-test")
    assert len(history) >= 4  # CREATED -> QUEUED -> RUNNING -> CHECKPOINT -> SUCCEEDED
    states = [h["to_state"] for h in history]
    assert "QUEUED" in states
    assert "RUNNING" in states
    assert "CHECKPOINT" in states
    assert "SUCCEEDED" in states
