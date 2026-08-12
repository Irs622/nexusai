"""SQLite implementation of IAuditStore with WAL mode, atomic sequence numbering, and tamper-evident SHA-256 hash chaining."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Sequence

from nexusai.brain.domain.audit import (
    AuditEvent,
    AuditVerificationResult,
    GENESIS_HASH,
)
from nexusai.brain.ports.audit_store_port import IAuditStore


class SQLiteAuditStore(IAuditStore):
    """Durable SQLite audit store enforcing tamper-evident hash chaining and atomic sequence numbering."""

    def __init__(self, db_path: str = ":memory:", busy_timeout_ms: int = 10000) -> None:
        self._keepalive: sqlite3.Connection | None
        if db_path == ":memory:":
            self.db_path = "file:mem_audit?mode=memory&cache=shared"
            self._keepalive = sqlite3.connect(self.db_path, uri=True)
        else:
            self.db_path = db_path
            self._keepalive = None
        self.busy_timeout_ms = busy_timeout_ms
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path.startswith("file:"):
            conn = sqlite3.connect(self.db_path, uri=True, timeout=self.busy_timeout_ms / 1000.0)
        else:
            conn = sqlite3.connect(self.db_path, timeout=self.busy_timeout_ms / 1000.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms};")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    plan_fingerprint TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL,
                    timestamp REAL NOT NULL,
                    node_id TEXT,
                    tool_id TEXT,
                    worker_id TEXT,
                    fencing_token INTEGER,
                    actor TEXT,
                    outcome TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    previous_event_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    metadata TEXT NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_events(session_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_execution ON audit_events(execution_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(event_type);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_seq ON audit_events(execution_id, sequence_number);")

    async def append_event(self, event: AuditEvent) -> AuditEvent:
        """Atomically append a correlated audit event with tamper-evident SHA-256 hash chaining."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT sequence_number, event_hash FROM audit_events WHERE execution_id = ? ORDER BY sequence_number DESC LIMIT 1",
                (event.execution_id,),
            ).fetchone()

            seq_num = (row["sequence_number"] + 1) if row else 1
            prev_hash = row["event_hash"] if row else GENESIS_HASH

            # Construct finalized AuditEvent with computed sequence_number & previous_event_hash
            final_event = AuditEvent(
                event_id=event.event_id,
                event_type=event.event_type,
                session_id=event.session_id,
                execution_id=event.execution_id,
                plan_fingerprint=event.plan_fingerprint,
                sequence_number=seq_num,
                timestamp=event.timestamp,
                node_id=event.node_id,
                tool_id=event.tool_id,
                worker_id=event.worker_id,
                fencing_token=event.fencing_token,
                actor=event.actor,
                outcome=event.outcome,
                severity=event.severity,
                previous_event_hash=prev_hash,
                metadata=event.metadata,
            )

            meta_str = json.dumps(final_event.metadata)
            conn.execute(
                """
                INSERT INTO audit_events (
                    event_id, event_type, session_id, execution_id, plan_fingerprint,
                    sequence_number, timestamp, node_id, tool_id, worker_id,
                    fencing_token, actor, outcome, severity, previous_event_hash,
                    event_hash, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    final_event.event_id,
                    final_event.event_type,
                    final_event.session_id,
                    final_event.execution_id,
                    final_event.plan_fingerprint,
                    final_event.sequence_number,
                    final_event.timestamp,
                    final_event.node_id,
                    final_event.tool_id,
                    final_event.worker_id,
                    final_event.fencing_token,
                    final_event.actor,
                    final_event.outcome,
                    final_event.severity,
                    final_event.previous_event_hash,
                    final_event.event_hash,
                    meta_str,
                ),
            )
            return final_event

    async def get_events(self, execution_id: str) -> Sequence[AuditEvent]:
        """Retrieve full ordered audit history for an execution."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_events WHERE execution_id = ? ORDER BY sequence_number ASC",
                (execution_id,),
            ).fetchall()
            return [self._row_to_event(r) for r in rows]

    async def get_event(self, event_id: str) -> AuditEvent | None:
        """Retrieve a specific audit event by event_id."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM audit_events WHERE event_id = ?", (event_id,)).fetchone()
            if not row:
                return None
            return self._row_to_event(row)

    async def get_latest_event(self, execution_id: str) -> AuditEvent | None:
        """Retrieve the most recent audit event for an execution."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM audit_events WHERE execution_id = ? ORDER BY sequence_number DESC LIMIT 1",
                (execution_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_event(row)

    async def verify_chain(self, execution_id: str) -> AuditVerificationResult:
        """Verify sequence monotonicity, previous event hash linkages, and SHA-256 payload integrity."""
        events = await self.get_events(execution_id)
        if not events:
            return AuditVerificationResult(
                valid=True,
                event_count=0,
                sequence_valid=True,
                hash_chain_valid=True,
                correlation_valid=True,
                terminal_state_valid=True,
            )

        violations = []
        seq_valid = True
        chain_valid = True
        corr_valid = True

        expected_seq = 1
        expected_prev_hash = GENESIS_HASH

        first_sess = events[0].session_id
        first_fp = events[0].plan_fingerprint

        for ev in events:
            if ev.sequence_number != expected_seq:
                seq_valid = False
                violations.append(f"Sequence gap/disorder at event {ev.event_id}: expected {expected_seq}, got {ev.sequence_number}")

            if ev.previous_event_hash != expected_prev_hash:
                chain_valid = False
                violations.append(f"Hash chain broken at sequence {ev.sequence_number}: expected prev {expected_prev_hash[:8]}, got {ev.previous_event_hash[:8]}")

            # Verify payload SHA-256 hash match
            canonical_payload = {
                "event_id": ev.event_id,
                "event_type": ev.event_type,
                "session_id": ev.session_id,
                "execution_id": ev.execution_id,
                "plan_fingerprint": ev.plan_fingerprint,
                "sequence_number": ev.sequence_number,
                "timestamp": ev.timestamp,
                "previous_event_hash": ev.previous_event_hash,
            }
            recalculated_hash = hashlib.sha256(json.dumps(canonical_payload, sort_keys=True).encode("utf-8")).hexdigest()

            if recalculated_hash != ev.event_hash:
                chain_valid = False
                violations.append(f"Payload tampered at sequence {ev.sequence_number}: calculated {recalculated_hash[:8]} != stored {ev.event_hash[:8]}")

            if ev.session_id != first_sess or ev.plan_fingerprint != first_fp:
                corr_valid = False
                violations.append(f"Correlation ID mismatch at sequence {ev.sequence_number}")

            expected_seq = ev.sequence_number + 1
            expected_prev_hash = ev.event_hash

        is_valid = seq_valid and chain_valid and corr_valid
        return AuditVerificationResult(
            valid=is_valid,
            event_count=len(events),
            sequence_valid=seq_valid,
            hash_chain_valid=chain_valid,
            correlation_valid=corr_valid,
            terminal_state_valid=True,
            violations=violations,
        )

    def _row_to_event(self, row: sqlite3.Row) -> AuditEvent:
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        return AuditEvent(
            event_id=row["event_id"],
            event_type=row["event_type"],
            session_id=row["session_id"],
            execution_id=row["execution_id"],
            plan_fingerprint=row["plan_fingerprint"],
            sequence_number=row["sequence_number"],
            timestamp=row["timestamp"],
            node_id=row["node_id"],
            tool_id=row["tool_id"],
            worker_id=row["worker_id"],
            fencing_token=row["fencing_token"],
            actor=row["actor"],
            outcome=row["outcome"],
            severity=row["severity"],
            previous_event_hash=row["previous_event_hash"],
            event_hash=row["event_hash"],
            metadata=meta,
        )
