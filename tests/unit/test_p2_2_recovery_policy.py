"""Unit tests for P2-2 Failure Recovery Policy Engine, Idempotency Keys, and Failure Classification."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from typing import Any
import pytest

from nexusai.brain.domain.agent import FailureReason, PlanGraph, PlanGraphNode, PlanStep
from nexusai.brain.domain.execution_state import (
    ExecutionRecord,
    ExecutionStatus,
    NodeExecutionRecord,
    NodeExecutionStatus,
    compute_plan_graph_hash,
)
from nexusai.brain.domain.recovery import (
    FailureClass,
    RecoveryAction,
    RecoveryPolicyEngine,
    ToolExecutionPolicy,
    classify_failure,
    generate_idempotency_key,
)
from nexusai.brain.ports.reconciliation_port import DefaultReconciliationAdapter
from nexusai.brain.ports.tool_port import ToolExecutionResult
from nexusai.infrastructure.persistence.sqlite_execution_store import SQLiteExecutionStateStore


def test_failure_classification() -> None:
    """Test classification of runtime failures into FailureClass taxonomy."""
    assert classify_failure(error_message="Connection timed out") == FailureClass.TIMEOUT
    assert classify_failure(error_message="401 Unauthorized") == FailureClass.AUTHENTICATION_ERROR
    assert classify_failure(error_message="403 Forbidden") == FailureClass.AUTHORIZATION_ERROR
    assert classify_failure(error_message="404 Tool not found") == FailureClass.TOOL_NOT_FOUND
    assert classify_failure(error_message="Invalid argument passed") == FailureClass.INVALID_ARGUMENT
    assert classify_failure(error_message="429 Rate limit exceeded") == FailureClass.RATE_LIMITED
    assert classify_failure(error_message="Connection refused socket error") == FailureClass.NETWORK_ERROR
    assert classify_failure(error_message="Unrecognized error message") == FailureClass.UNKNOWN_ERROR


def test_idempotency_key_stability() -> None:
    """Test J & K: Idempotency key is deterministic and stable across retries and process restarts."""
    key1 = generate_idempotency_key("exec-100", 5)
    key2 = generate_idempotency_key("exec-100", 5)
    assert key1 == key2
    assert "exec-100-5" in key1

    key_diff = generate_idempotency_key("exec-100", 6)
    assert key1 != key_diff


def test_A_idempotent_transient_failure_retries() -> None:
    """Test A: Transient failure on an idempotent tool produces RETRY decision."""
    policy = ToolExecutionPolicy(idempotent=True, retryable=True, side_effecting=False, max_retries=3)
    decision = RecoveryPolicyEngine.evaluate(policy, FailureClass.TIMEOUT, attempt_number=1)

    assert decision.action == RecoveryAction.RETRY
    assert decision.retry_delay_seconds > 0


def test_B_retry_count_respects_max_retries() -> None:
    """Test B: Exceeding max_retries produces FAIL decision."""
    policy = ToolExecutionPolicy(idempotent=True, max_retries=3)
    decision = RecoveryPolicyEngine.evaluate(policy, FailureClass.TIMEOUT, attempt_number=3)

    assert decision.action == RecoveryAction.FAIL
    assert "Exceeded max retry budget" in decision.reason


def test_C_and_D_exponential_backoff_calculation_and_cap() -> None:
    """Test C & D: Exponential backoff calculation and max delay cap."""
    policy = ToolExecutionPolicy(backoff_factor=2.0, max_backoff_seconds=5.0)

    delay1 = RecoveryPolicyEngine.calculate_backoff(policy, attempt_number=1)  # 0.5 * 2^0 = 0.5
    delay2 = RecoveryPolicyEngine.calculate_backoff(policy, attempt_number=2)  # 0.5 * 2^1 = 1.0
    delay3 = RecoveryPolicyEngine.calculate_backoff(policy, attempt_number=3)  # 0.5 * 2^2 = 2.0
    delay4 = RecoveryPolicyEngine.calculate_backoff(policy, attempt_number=4)  # 0.5 * 2^3 = 4.0
    delay5 = RecoveryPolicyEngine.calculate_backoff(policy, attempt_number=5)  # 0.5 * 2^4 = 8.0 -> capped at 5.0

    assert delay1 == 0.5
    assert delay2 == 1.0
    assert delay3 == 2.0
    assert delay4 == 4.0
    assert delay5 == 5.0  # Capped at max_backoff_seconds


def test_E_and_F_non_idempotent_side_effect_produces_reconcile() -> None:
    """Test E & F: Non-idempotent side-effecting failure or timeout produces RECONCILE decision."""
    policy = ToolExecutionPolicy(idempotent=False, side_effecting=True, max_retries=3)

    decision_fail = RecoveryPolicyEngine.evaluate(policy, FailureClass.TRANSIENT_ERROR, attempt_number=1)
    assert decision_fail.action == RecoveryAction.RECONCILE

    decision_timeout = RecoveryPolicyEngine.evaluate(policy, FailureClass.TIMEOUT, attempt_number=1)
    assert decision_timeout.action == RecoveryAction.RECONCILE


def test_G_unknown_failure_conservative_decision() -> None:
    """Test G: Unknown failure on side-effecting tool is conservative and produces RECONCILE."""
    policy = ToolExecutionPolicy(idempotent=False, side_effecting=True)
    decision = RecoveryPolicyEngine.evaluate(policy, FailureClass.UNKNOWN_ERROR, attempt_number=1)
    assert decision.action == RecoveryAction.RECONCILE


def test_H_non_retryable_auth_failure_fails() -> None:
    """Test H: Authentication failure produces FAIL decision without retrying."""
    policy = ToolExecutionPolicy(idempotent=True, max_retries=5)
    decision = RecoveryPolicyEngine.evaluate(policy, FailureClass.AUTHENTICATION_ERROR, attempt_number=1)
    assert decision.action == RecoveryAction.FAIL
    assert "Non-retryable" in decision.reason


def test_I_circuit_breaker_open_prevents_retry() -> None:
    """Test I: CircuitBreaker OPEN state forces FAIL decision without retry."""
    policy = ToolExecutionPolicy(idempotent=True, max_retries=5)
    decision = RecoveryPolicyEngine.evaluate(policy, FailureClass.TIMEOUT, attempt_number=1, cb_is_open=True)
    assert decision.action == RecoveryAction.FAIL
    assert "CircuitBreaker is OPEN" in decision.reason


@pytest.mark.asyncio
async def test_O_database_migration_from_v1_to_v2() -> None:
    """Test O: SQLiteExecutionStateStore safely migrates version 1 database to version 2 schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        # Create legacy version 1 database manually
        import sqlite3
        conn = sqlite3.connect(db_path)
        with conn:
            conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at REAL);")
            conn.execute("INSERT INTO schema_migrations VALUES (1, ?);", (time.time(),))
            conn.execute("""
                CREATE TABLE executions (
                    execution_id TEXT PRIMARY KEY, plan_id TEXT, graph_hash TEXT,
                    status TEXT, schema_version INTEGER, created_at REAL, updated_at REAL
                )
            """)
            conn.execute("""
                CREATE TABLE node_executions (
                    execution_id TEXT, node_id TEXT, status TEXT, tool_name TEXT,
                    arguments_json TEXT, output_json TEXT, error_message TEXT,
                    attempt_count INTEGER, started_at REAL, completed_at REAL, updated_at REAL,
                    PRIMARY KEY (execution_id, node_id)
                )
            """)
        conn.close()

        # Instantiate SQLiteExecutionStateStore - triggers version 2 migration
        store = SQLiteExecutionStateStore(db_path=db_path)
        record = ExecutionRecord(
            execution_id="exec-v2",
            plan_id="plan-v2",
            graph_hash="hash-v2",
            node_records={1: NodeExecutionRecord(execution_id="exec-v2", node_id=1)},
        )
        await store.create_execution(record)

        loaded = await store.load_execution("exec-v2")
        assert loaded is not None
        assert loaded.schema_version == 2
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    test_failure_classification()
    test_idempotency_key_stability()
    test_A_idempotent_transient_failure_retries()
    test_B_retry_count_respects_max_retries()
    test_C_and_D_exponential_backoff_calculation_and_cap()
    test_E_and_F_non_idempotent_side_effect_produces_reconcile()
    test_G_unknown_failure_conservative_decision()
    test_H_non_retryable_auth_failure_fails()
    test_I_circuit_breaker_open_prevents_retry()
    asyncio.run(test_O_database_migration_from_v1_to_v2())
    print("ALL P2-2 RECOVERY POLICY UNIT TESTS PASSED SUCCESSFULLY!")
