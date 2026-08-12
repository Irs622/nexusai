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

    def __init__(self, db_path: str = ":memory:", max_payload_bytes: int = MAX_PAYLOAD_BYTES) -> None:
        self.db_path = db_path
        self.max_payload_bytes = max_payload_bytes
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and configure a thread-local SQLite connection with WAL mode."""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
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
                    conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (1, ?)", (time.time(),))
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
                    conn.execute("INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (2, ?)", (time.time(),))
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
                    INSERT INTO executions (execution_id, plan_id, graph_hash, status, schema_version, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.execution_id,
                        record.plan_id,
                        record.graph_hash,
                        record.status.value,
                        2,
                        record.created_at,
                        record.updated_at,
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

            exec_record = ExecutionRecord(
                execution_id=row["execution_id"],
                plan_id=row["plan_id"],
                graph_hash=row["graph_hash"],
                status=ExecutionStatus(row["status"]),
                schema_version=row["schema_version"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
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
                    idempotency_key=n_row["idempotency_key"] if "idempotency_key" in n_row.keys() else None,
                    last_failure_class=n_row["last_failure_class"] if "last_failure_class" in n_row.keys() else None,
                    last_recovery_action=n_row["last_recovery_action"] if "last_recovery_action" in n_row.keys() else None,
                    next_retry_at=n_row["next_retry_at"] if "next_retry_at" in n_row.keys() else None,
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
            self._sync_save_recovery_decision_atomically, execution_id, str(node_id), status, decision
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
