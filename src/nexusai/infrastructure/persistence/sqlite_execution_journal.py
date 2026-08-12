"""SQLite implementation of IExecutionJournal with WAL mode and atomic write-ahead lifecycle logging."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Sequence

from nexusai.brain.domain.execution_recovery import (
    JournalEntry,
    JournalLifecyclePhase,
    RecoveryStatus,
    TERMINAL_JOURNAL_PHASES,
)
from nexusai.brain.domain.tool_registry import ToolIdempotency
from nexusai.brain.ports.execution_recovery_port import IExecutionJournal


class SQLiteExecutionJournal(IExecutionJournal):
    """Durable SQLite write-ahead journal recording lifecycle phase transitions and recovery classifications."""

    def __init__(self, db_path: str = ":memory:", busy_timeout_ms: int = 10000) -> None:
        self.db_path = db_path
        self.busy_timeout_ms = busy_timeout_ms
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=self.busy_timeout_ms / 1000.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms};")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_journal (
                    entry_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    plan_fingerprint TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    tool_id TEXT NOT NULL,
                    action_digest TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    attempt INTEGER NOT NULL,
                    governance_reservation_id TEXT,
                    approval_grant_id TEXT,
                    idempotency_key TEXT NOT NULL,
                    idempotency TEXT NOT NULL,
                    recovery_status TEXT NOT NULL,
                    audit_hash TEXT NOT NULL,
                    metadata TEXT NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_session ON execution_journal(session_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_execution ON execution_journal(execution_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_phase ON execution_journal(phase);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_timestamp ON execution_journal(timestamp);")

    async def append_entry(self, entry: JournalEntry) -> JournalEntry:
        """Append a durable lifecycle transition entry to the write-ahead journal."""
        meta_str = json.dumps(entry.metadata)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO execution_journal (
                    entry_id, session_id, execution_id, plan_fingerprint, node_id,
                    tool_id, action_digest, phase, timestamp, attempt,
                    governance_reservation_id, approval_grant_id, idempotency_key,
                    idempotency, recovery_status, audit_hash, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.entry_id,
                    entry.session_id,
                    entry.execution_id,
                    entry.plan_fingerprint,
                    entry.node_id,
                    entry.tool_id,
                    entry.action_digest,
                    entry.phase.value,
                    entry.timestamp,
                    entry.attempt,
                    entry.governance_reservation_id,
                    entry.approval_grant_id,
                    entry.idempotency_key,
                    entry.idempotency.value,
                    entry.recovery_status.value,
                    entry.audit_hash,
                    meta_str,
                ),
            )
        return entry

    async def get_latest_entry(self, execution_id: str) -> JournalEntry | None:
        """Retrieve the most recent journal entry for an execution."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM execution_journal WHERE execution_id = ? ORDER BY timestamp DESC, entry_id DESC LIMIT 1",
                (execution_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_entry(row)

    async def get_history(self, execution_id: str) -> Sequence[JournalEntry]:
        """Retrieve full ordered lifecycle journal history for an execution."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM execution_journal WHERE execution_id = ? ORDER BY timestamp ASC, entry_id ASC",
                (execution_id,),
            ).fetchall()
            return [self._row_to_entry(r) for r in rows]

    async def get_active_executions(self) -> Sequence[str]:
        """Retrieve all execution_ids currently in non-terminal phases."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT DISTINCT execution_id FROM execution_journal").fetchall()
            active = []
            for r in rows:
                exec_id = r["execution_id"]
                latest = await self.get_latest_entry(exec_id)
                if latest and latest.phase not in TERMINAL_JOURNAL_PHASES:
                    active.append(exec_id)
            return active

    async def update_recovery_status(self, execution_id: str, status: RecoveryStatus) -> None:
        """Update the crash recovery classification status for an execution."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE execution_journal SET recovery_status = ? WHERE execution_id = ?",
                (status.value, execution_id),
            )

    def _row_to_entry(self, row: sqlite3.Row) -> JournalEntry:
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        return JournalEntry(
            entry_id=row["entry_id"],
            session_id=row["session_id"],
            execution_id=row["execution_id"],
            plan_fingerprint=row["plan_fingerprint"],
            node_id=row["node_id"],
            tool_id=row["tool_id"],
            action_digest=row["action_digest"],
            phase=JournalLifecyclePhase(row["phase"]),
            timestamp=row["timestamp"],
            attempt=row["attempt"],
            governance_reservation_id=row["governance_reservation_id"],
            approval_grant_id=row["approval_grant_id"],
            idempotency_key=row["idempotency_key"],
            idempotency=ToolIdempotency(row["idempotency"]),
            recovery_status=RecoveryStatus(row["recovery_status"]),
            audit_hash=row["audit_hash"],
            metadata=meta,
        )
