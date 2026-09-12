"""SQLite implementation of IExecutionStateStore with WAL mode, schema version 2 migration, and atomic recovery checkpoints."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from typing import Any

from nexusai.brain.domain.execution_state import (
    ExecutionRecord,
    ExecutionStatus,
    NodeExecutionRecord,
    NodeExecutionStatus,
)
from nexusai.brain.domain.recovery import RecoveryDecision
from nexusai.brain.ports.execution_state_port import IExecutionStateStore
from nexusai.brain.ports.tool_port import ToolExecutionResult

MAX_PAYLOAD_BYTES = 1_048_576  # 1MB output payload size limit


class SerializationError(ValueError):
    """Raised when tool output or arguments cannot be JSON-serialized safely."""

    pass


class SQLiteExecutionStateStore(IExecutionStateStore):
    """Durable SQLite storage engine with WAL mode, schema version 2 migration, and atomic recovery checkpoints."""

    def __init__(
        self, db_path: str = ":memory:", max_payload_bytes: int = MAX_PAYLOAD_BYTES
    ) -> None:
        if db_path == ":memory:":
            self._is_memory = True
            self._db_uri = f"file:memdb_{id(self)}_{time.time_ns()}?mode=memory&cache=shared"
            self._keepalive: sqlite3.Connection | None = sqlite3.connect(
                self._db_uri, uri=True, check_same_thread=False
            )
            self.db_path = self._db_uri
        else:
            self._is_memory = False
            self._keepalive = None
            self.db_path = db_path
        self.max_payload_bytes = max_payload_bytes
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and configure a thread-local SQLite connection with WAL mode."""
        conn = sqlite3.connect(self.db_path, timeout=5.0, uri=self._is_memory)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        """Initialize database schema and execute schema version 2 migration if upgrading from version 1."""
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at REAL NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS executions (
                        execution_id TEXT PRIMARY KEY,
                        plan_id TEXT NOT NULL,
                        graph_hash TEXT NOT NULL,
                        status TEXT NOT NULL,
                        schema_version INTEGER NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS node_executions (
                        execution_id TEXT NOT NULL,
                        node_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        tool_name TEXT,
                        arguments_json TEXT,
                        output_json TEXT,
                        error_message TEXT,
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        idempotency_key TEXT,
                        last_failure_class TEXT,
                        last_recovery_action TEXT,
                        next_retry_at REAL,
                        started_at REAL,
                        completed_at REAL,
                        updated_at REAL NOT NULL,
                        PRIMARY KEY (execution_id, node_id),
                        FOREIGN KEY (execution_id) REFERENCES executions(execution_id) ON DELETE CASCADE
                    )
                """)

                # Check current schema version
                row = conn.execute("SELECT MAX(version) as ver FROM schema_migrations").fetchone()
                current_ver = row["ver"] if row and row["ver"] is not None else 0

                if current_ver < 1:
                    conn.execute(
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (1, ?)",
                        (time.time(),),
                    )
                    current_ver = 1

                if current_ver < 2:
                    # Idempotent migration adding P2-2 recovery columns
                    for col_def in [
                        "idempotency_key TEXT",
                        "last_failure_class TEXT",
                        "last_recovery_action TEXT",
                        "next_retry_at REAL",
                    ]:
                        try:
                            conn.execute(f"ALTER TABLE node_executions ADD COLUMN {col_def}")
                        except sqlite3.OperationalError:
                            pass
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (2, ?)",
                        (time.time(),),
                    )
                    current_ver = 2

                if current_ver < 3:
                    # Migration version 3: durable execution state machine, worker leases, fencing tokens, and transitions
                    for col_def in [
                        "worker_id TEXT",
                        "fencing_token INTEGER NOT NULL DEFAULT 0",
                        "actor TEXT NOT NULL DEFAULT 'system'",
                        "tenant_id TEXT NOT NULL DEFAULT 'default'",
                        "idempotency_key TEXT",
                        "retry_count INTEGER NOT NULL DEFAULT 0",
                        "cancellation_requested INTEGER NOT NULL DEFAULT 0",
                    ]:
                        try:
                            conn.execute(f"ALTER TABLE executions ADD COLUMN {col_def}")
                        except sqlite3.OperationalError:
                            pass

                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS execution_state_transitions (
                            transition_id TEXT PRIMARY KEY,
                            execution_id TEXT NOT NULL,
                            from_state TEXT NOT NULL,
                            to_state TEXT NOT NULL,
                            actor TEXT NOT NULL,
                            worker_id TEXT NOT NULL,
                            fencing_token INTEGER NOT NULL,
                            timestamp REAL NOT NULL,
                            reason TEXT,
                            metadata_json TEXT,
                            FOREIGN KEY (execution_id) REFERENCES executions(execution_id) ON DELETE CASCADE
                        )
                    """)
                    conn.execute("""
                        CREATE INDEX IF NOT EXISTS idx_exec_transitions
                        ON execution_state_transitions(execution_id, timestamp)
                    """)
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (3, ?)",
                        (time.time(),),
                    )
        finally:
            conn.close()

    def _serialize_json(self, value: Any) -> str | None:
        """Safely serialize a value to JSON, rejecting non-serializable objects and large payloads."""
        if value is None:
            return None
        try:
            serialized = json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise SerializationError(f"Payload is not JSON-serializable: {exc}") from exc

        if len(serialized.encode("utf-8")) > self.max_payload_bytes:
            raise SerializationError(
                f"Payload size ({len(serialized)} bytes) exceeds max limit ({self.max_payload_bytes} bytes)"
            )
        return serialized

    def _deserialize_json(self, value: str | None) -> Any:
        """Safely deserialize JSON string to Python object."""
        if value is None:
            return None
        return json.loads(value)

    # ------------------------------------------------------------------
    # Async IExecutionStateStore Protocol Implementation
    # ------------------------------------------------------------------

    async def create_execution(self, record: ExecutionRecord) -> None:
        """Persist a new execution record and initialize node checkpoints."""
        await asyncio.to_thread(self._sync_create_execution, record)

    def _sync_create_execution(self, record: ExecutionRecord) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO executions (
                        execution_id, plan_id, graph_hash, status, schema_version, created_at, updated_at,
                        worker_id, fencing_token, actor, tenant_id, idempotency_key, retry_count, cancellation_requested
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.execution_id,
                        record.plan_id,
                        record.graph_hash,
                        record.status.value,
                        3,
                        record.created_at,
                        record.updated_at,
                        record.worker_id,
                        record.fencing_token,
                        record.actor,
                        record.tenant_id,
                        record.idempotency_key,
                        record.retry_count,
                        1 if record.cancellation_requested else 0,
                    ),
                )
                for node_id, node_rec in record.node_records.items():
                    args_json = self._serialize_json(node_rec.arguments)
                    conn.execute(
                        """
                        INSERT INTO node_executions (
                            execution_id, node_id, status, tool_name, arguments_json, output_json,
                            error_message, attempt_count, idempotency_key, last_failure_class,
                            last_recovery_action, next_retry_at, started_at, completed_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record.execution_id,
                            str(node_id),
                            node_rec.status.value,
                            node_rec.tool_name,
                            args_json,
                            None,
                            node_rec.error_message,
                            node_rec.attempt_count,
                            node_rec.idempotency_key,
                            node_rec.last_failure_class,
                            node_rec.last_recovery_action,
                            node_rec.next_retry_at,
                            node_rec.started_at,
                            node_rec.completed_at,
                            node_rec.updated_at,
                        ),
                    )
        finally:
            conn.close()

    async def load_execution(self, execution_id: str) -> ExecutionRecord | None:
        """Load an execution record and its node checkpoints from durable storage."""
        return await asyncio.to_thread(self._sync_load_execution, execution_id)

    def _sync_load_execution(self, execution_id: str) -> ExecutionRecord | None:
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM executions WHERE execution_id = ?", (execution_id,)
            ).fetchone()
            if row is None:
                return None

            row_keys = row.keys() if hasattr(row, "keys") else []
            exec_record = ExecutionRecord(
                execution_id=row["execution_id"],
                plan_id=row["plan_id"],
                graph_hash=row["graph_hash"],
                status=ExecutionStatus(row["status"]),
                schema_version=row["schema_version"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                worker_id=row["worker_id"] if "worker_id" in row_keys else None,
                fencing_token=row["fencing_token"] if "fencing_token" in row_keys else 0,
                actor=row["actor"] if "actor" in row_keys else "system",
                tenant_id=row["tenant_id"] if "tenant_id" in row_keys else "default",
                idempotency_key=row["idempotency_key"] if "idempotency_key" in row_keys else None,
                retry_count=row["retry_count"] if "retry_count" in row_keys else 0,
                cancellation_requested=(
                    bool(row["cancellation_requested"])
                    if "cancellation_requested" in row_keys
                    else False
                ),
            )

            node_rows = conn.execute(
                "SELECT * FROM node_executions WHERE execution_id = ?", (execution_id,)
            ).fetchall()

            for n_row in node_rows:
                raw_node_id = n_row["node_id"]
                node_id: Any = int(raw_node_id) if raw_node_id.isdigit() else raw_node_id

                node_rec = NodeExecutionRecord(
                    execution_id=execution_id,
                    node_id=node_id,
                    status=NodeExecutionStatus(n_row["status"]),
                    tool_name=n_row["tool_name"],
                    arguments=self._deserialize_json(n_row["arguments_json"]) or {},
                    output=self._deserialize_json(n_row["output_json"]),
                    error_message=n_row["error_message"],
                    attempt_count=n_row["attempt_count"],
                    idempotency_key=(
                        n_row["idempotency_key"] if "idempotency_key" in n_row.keys() else None
                    ),
                    last_failure_class=(
                        n_row["last_failure_class"]
                        if "last_failure_class" in n_row.keys()
                        else None
                    ),
                    last_recovery_action=(
                        n_row["last_recovery_action"]
                        if "last_recovery_action" in n_row.keys()
                        else None
                    ),
                    next_retry_at=(
                        n_row["next_retry_at"] if "next_retry_at" in n_row.keys() else None
                    ),
                    started_at=n_row["started_at"],
                    completed_at=n_row["completed_at"],
                    updated_at=n_row["updated_at"],
                )
                exec_record.node_records[node_id] = node_rec

            return exec_record
        finally:
            conn.close()

    async def mark_node_running(self, execution_id: str, node_id: Any) -> None:
        """Checkpoint node transition to RUNNING state."""
        await asyncio.to_thread(self._sync_mark_node_running, execution_id, str(node_id))

    def _sync_mark_node_running(self, execution_id: str, str_node_id: str) -> None:
        conn = self._get_connection()
        now = time.time()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE node_executions
                    SET status = ?, started_at = COALESCE(started_at, ?), attempt_count = attempt_count + 1, updated_at = ?
                    WHERE execution_id = ? AND node_id = ?
                    """,
                    (NodeExecutionStatus.RUNNING.value, now, now, execution_id, str_node_id),
                )
        finally:
            conn.close()

    async def save_node_result_atomically(
        self,
        execution_id: str,
        node_id: Any,
        status: NodeExecutionStatus,
        result: ToolExecutionResult,
    ) -> None:
        """Atomically persist tool execution output and terminal node status in a single transaction."""
        await asyncio.to_thread(
            self._sync_save_node_result_atomically, execution_id, str(node_id), status, result
        )

    def _sync_save_node_result_atomically(
        self,
        execution_id: str,
        str_node_id: str,
        status: NodeExecutionStatus,
        result: ToolExecutionResult,
    ) -> None:
        output_json = self._serialize_json(result.output)
        now = time.time()
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE node_executions
                    SET status = ?, output_json = ?, error_message = ?, completed_at = ?, updated_at = ?
                    WHERE execution_id = ? AND node_id = ?
                    """,
                    (
                        status.value,
                        output_json,
                        result.error_message,
                        now,
                        now,
                        execution_id,
                        str_node_id,
                    ),
                )
        finally:
            conn.close()

    async def save_recovery_decision_atomically(
        self,
        execution_id: str,
        node_id: Any,
        status: NodeExecutionStatus,
        decision: RecoveryDecision,
    ) -> None:
        """Atomically persist recovery policy decision, idempotency key, failure class, and next_retry_at timestamp."""
        await asyncio.to_thread(
            self._sync_save_recovery_decision_atomically,
            execution_id,
            str(node_id),
            status,
            decision,
        )

    def _sync_save_recovery_decision_atomically(
        self,
        execution_id: str,
        str_node_id: str,
        status: NodeExecutionStatus,
        decision: RecoveryDecision,
    ) -> None:
        now = time.time()
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE node_executions
                    SET status = ?, idempotency_key = ?, last_failure_class = ?,
                        last_recovery_action = ?, next_retry_at = ?, updated_at = ?
                    WHERE execution_id = ? AND node_id = ?
                    """,
                    (
                        status.value,
                        decision.idempotency_key,
                        decision.failure_class.value,
                        decision.action.value,
                        decision.next_retry_at,
                        now,
                        execution_id,
                        str_node_id,
                    ),
                )
        finally:
            conn.close()

    async def mark_node_cancelled(self, execution_id: str, node_id: Any) -> None:
        """Checkpoint node transition to CANCELLED state."""
        await asyncio.to_thread(self._sync_mark_node_cancelled, execution_id, str(node_id))

    def _sync_mark_node_cancelled(self, execution_id: str, str_node_id: str) -> None:
        conn = self._get_connection()
        now = time.time()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE node_executions
                    SET status = ?, updated_at = ?
                    WHERE execution_id = ? AND node_id = ?
                    """,
                    (NodeExecutionStatus.CANCELLED.value, now, execution_id, str_node_id),
                )
        finally:
            conn.close()

    async def update_execution_status(
        self,
        execution_id: str,
        status: ExecutionStatus,
    ) -> None:
        """Update overall execution status."""
        await asyncio.to_thread(self._sync_update_execution_status, execution_id, status)

    def _sync_update_execution_status(
        self,
        execution_id: str,
        status: ExecutionStatus,
    ) -> None:
        conn = self._get_connection()
        now = time.time()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE executions
                    SET status = ?, updated_at = ?
                    WHERE execution_id = ?
                    """,
                    (status.value, now, execution_id),
                )
        finally:
            conn.close()

    async def record_state_transition(
        self,
        execution_id: str,
        from_state: str,
        to_state: str,
        actor: str,
        worker_id: str,
        fencing_token: int,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Record an atomic, durable, actor-attributed, idempotent state transition with fencing check."""
        return await asyncio.to_thread(
            self._sync_record_state_transition,
            execution_id,
            from_state,
            to_state,
            actor,
            worker_id,
            fencing_token,
            reason,
            metadata,
        )

    def _sync_record_state_transition(
        self,
        execution_id: str,
        from_state: str,
        to_state: str,
        actor: str,
        worker_id: str,
        fencing_token: int,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        conn = self._get_connection()
        try:
            with conn:
                row = conn.execute(
                    "SELECT status, fencing_token FROM executions WHERE execution_id = ?",
                    (execution_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f"Execution '{execution_id}' not found in state store")

                current_status = row["status"]
                current_token = row["fencing_token"] or 0

                # Idempotency check: same state transition applied twice is a no-op!
                if current_status == to_state:
                    return True

                # Fencing token check: reject stale worker holding a token smaller than active token
                if fencing_token > 0 and fencing_token < current_token:
                    from nexusai.brain.domain.execution_coordination import FencingTokenError

                    raise FencingTokenError(
                        f"Fencing token rejection: incoming token {fencing_token} is smaller than current active token {current_token}"
                    )

                now = time.time()
                meta_json = self._serialize_json(metadata) if metadata else None
                trans_id = f"trans-{execution_id}-{time.time_ns()}-{fencing_token}"

                effective_token = max(fencing_token, current_token)

                conn.execute(
                    """
                    UPDATE executions
                    SET status = ?, worker_id = ?, fencing_token = ?, actor = ?, updated_at = ?
                    WHERE execution_id = ?
                    """,
                    (to_state, worker_id, effective_token, actor, now, execution_id),
                )

                conn.execute(
                    """
                    INSERT INTO execution_state_transitions (
                        transition_id, execution_id, from_state, to_state, actor,
                        worker_id, fencing_token, timestamp, reason, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trans_id,
                        execution_id,
                        current_status,
                        to_state,
                        actor,
                        worker_id,
                        effective_token,
                        now,
                        reason,
                        meta_json,
                    ),
                )
                return True
        finally:
            conn.close()

    async def get_state_history(self, execution_id: str) -> list[dict[str, Any]]:
        """Retrieve ordered history of execution state transitions."""
        return await asyncio.to_thread(self._sync_get_state_history, execution_id)

    def _sync_get_state_history(self, execution_id: str) -> list[dict[str, Any]]:
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM execution_state_transitions WHERE execution_id = ? ORDER BY timestamp ASC, transition_id ASC",
                (execution_id,),
            ).fetchall()
            history: list[dict[str, Any]] = []
            for r in rows:
                history.append(
                    {
                        "transition_id": r["transition_id"],
                        "execution_id": r["execution_id"],
                        "from_state": r["from_state"],
                        "to_state": r["to_state"],
                        "actor": r["actor"],
                        "worker_id": r["worker_id"],
                        "fencing_token": r["fencing_token"],
                        "timestamp": r["timestamp"],
                        "reason": r["reason"],
                        "metadata": self._deserialize_json(r["metadata_json"]) or {},
                    }
                )
            return history
        finally:
            conn.close()

    async def get_stale_or_running_executions(
        self, states: list[str] | None = None
    ) -> list[ExecutionRecord]:
        """Query executions currently in non-terminal states for crash recovery inspection."""
        return await asyncio.to_thread(self._sync_get_stale_or_running_executions, states)

    def _sync_get_stale_or_running_executions(
        self, states: list[str] | None = None
    ) -> list[ExecutionRecord]:
        conn = self._get_connection()
        try:
            target_states = states or [
                "RUNNING",
                "QUEUED",
                "CHECKPOINT",
                "RETRY_WAIT",
                "FAILED_RETRYABLE",
            ]
            placeholders = ",".join("?" for _ in target_states)
            rows = conn.execute(
                f"SELECT execution_id FROM executions WHERE status IN ({placeholders})",
                target_states,
            ).fetchall()
            records: list[ExecutionRecord] = []
            for r in rows:
                rec = self._sync_load_execution(r["execution_id"])
                if rec:
                    records.append(rec)
            return records
        finally:
            conn.close()

    async def mark_cancellation_requested(self, execution_id: str) -> None:
        """Atomically set cancellation_requested flag for an execution."""
        await asyncio.to_thread(self._sync_mark_cancellation_requested, execution_id)

    def _sync_mark_cancellation_requested(self, execution_id: str) -> None:
        conn = self._get_connection()
        now = time.time()
        try:
            with conn:
                conn.execute(
                    "UPDATE executions SET cancellation_requested = 1, updated_at = ? WHERE execution_id = ?",
                    (now, execution_id),
                )
        finally:
            conn.close()

    async def is_cancellation_requested(self, execution_id: str) -> bool:
        """Check whether cancellation has been requested or recorded for an execution."""
        return await asyncio.to_thread(self._sync_is_cancellation_requested, execution_id)

    def _sync_is_cancellation_requested(self, execution_id: str) -> bool:
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT cancellation_requested, status FROM executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if not row:
                return False
            return bool(row["cancellation_requested"]) or row["status"] == "CANCELLED"
        finally:
            conn.close()
