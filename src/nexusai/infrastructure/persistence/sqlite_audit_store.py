"""SQLite implementation of IAuditStore with WAL mode, atomic sequence numbering, and tamper-evident SHA-256 hash chaining."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from typing import Sequence
from uuid import uuid4

from nexusai.brain.domain.audit import (
    GENESIS_HASH,
    AuditEvent,
    AuditVerificationResult,
)
from nexusai.brain.ports.audit_store_port import IAuditStore


class SQLiteAuditStore(IAuditStore):
    """Durable SQLite append-only audit store enforcing tamper-evident hash chaining and atomic sequence numbering."""

    def __init__(self, db_path: str = ":memory:", busy_timeout_ms: int = 10000) -> None:
        self._keepalive: sqlite3.Connection | None
        if db_path == ":memory:":
            self.db_path = f"file:mem_audit_{uuid4().hex}?mode=memory&cache=shared"
            self._keepalive = sqlite3.connect(self.db_path, uri=True)
        else:
            self.db_path = db_path
            self._keepalive = None
        self.busy_timeout_ms = busy_timeout_ms
        self._write_lock = asyncio.Lock()
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
                    id TEXT PRIMARY KEY,
                    sequence INTEGER NOT NULL,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    tool_name TEXT,
                    outcome TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    execution_id TEXT NOT NULL DEFAULT '',
                    plan_fingerprint TEXT NOT NULL DEFAULT '',
                    node_id TEXT,
                    worker_id TEXT,
                    fencing_token INTEGER,
                    severity TEXT NOT NULL DEFAULT 'INFO',
                    event_id TEXT GENERATED ALWAYS AS (id) STORED,
                    sequence_number INTEGER GENERATED ALWAYS AS (sequence) STORED,
                    tool_id TEXT GENERATED ALWAYS AS (tool_name) STORED,
                    previous_event_hash TEXT GENERATED ALWAYS AS (previous_hash) STORED,
                    metadata TEXT GENERATED ALWAYS AS (metadata_json) STORED,
                    CONSTRAINT sequence_monotonic CHECK (sequence > 0),
                    CONSTRAINT unique_tenant_sequence UNIQUE (tenant_id, sequence)
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_events(tenant_id);")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_tenant_seq ON audit_events(tenant_id, sequence);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events(event_type);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_events(session_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_execution ON audit_events(execution_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_seq ON audit_events(execution_id, sequence);"
            )

    def seed_initial_events_if_empty(
        self, events: Sequence[AuditEvent] | None = None, tenant_id: str = "default"
    ) -> None:
        """Seed initial genesis events if the store is completely empty for specified tenant."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM audit_events WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
            if row and row["cnt"] > 0:
                return

            if not events:
                return

            for ev in events:
                meta_str = json.dumps(dict(ev.metadata), sort_keys=True, default=str)
                conn.execute(
                    """
                    INSERT INTO audit_events (
                        id, sequence, timestamp, event_type, actor, tenant_id,
                        tool_name, outcome, metadata_json, previous_hash, event_hash,
                        session_id, execution_id, plan_fingerprint, node_id, worker_id,
                        fencing_token, severity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ev.event_id,
                        ev.sequence_number,
                        ev.timestamp,
                        ev.event_type,
                        ev.actor,
                        ev.tenant_id,
                        ev.tool_id,
                        ev.outcome,
                        meta_str,
                        ev.previous_event_hash,
                        ev.event_hash,
                        ev.session_id,
                        ev.execution_id,
                        ev.plan_fingerprint,
                        ev.node_id,
                        ev.worker_id,
                        ev.fencing_token,
                        ev.severity,
                    ),
                )

    async def append_event(self, event: AuditEvent) -> AuditEvent:
        """Atomically append a correlated audit event with tamper-evident SHA-256 hash chaining."""
        async with self._write_lock:
            with self._get_connection() as conn:
                t_id = event.tenant_id if event.tenant_id else "default"

                # Check if this is a pre-sequenced event or needs monotonic sequence allocation
                if event.sequence_number > 0 and event.previous_event_hash:
                    seq_num = event.sequence_number
                    prev_hash = event.previous_event_hash
                else:
                    # Query latest event in tenant chain
                    row = conn.execute(
                        "SELECT sequence, event_hash FROM audit_events WHERE tenant_id = ? ORDER BY sequence DESC LIMIT 1",
                        (t_id,),
                    ).fetchone()

                    seq_num = (row["sequence"] + 1) if row else 1
                    prev_hash = row["event_hash"] if row else GENESIS_HASH

                final_event = AuditEvent(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    session_id=event.session_id,
                    execution_id=event.execution_id,
                    plan_fingerprint=event.plan_fingerprint,
                    sequence_number=seq_num,
                    timestamp=event.timestamp if event.timestamp > 0 else time.time(),
                    node_id=event.node_id,
                    tool_id=event.tool_id,
                    worker_id=event.worker_id,
                    fencing_token=event.fencing_token,
                    actor=event.actor if event.actor else "anonymous",
                    tenant_id=t_id,
                    outcome=event.outcome,
                    severity=event.severity,
                    previous_event_hash=prev_hash,
                    metadata=dict(event.metadata),
                )

                meta_str = json.dumps(dict(final_event.metadata), sort_keys=True, default=str)
                conn.execute(
                    """
                    INSERT INTO audit_events (
                        id, sequence, timestamp, event_type, actor, tenant_id,
                        tool_name, outcome, metadata_json, previous_hash, event_hash,
                        session_id, execution_id, plan_fingerprint, node_id, worker_id,
                        fencing_token, severity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        final_event.event_id,
                        final_event.sequence_number,
                        final_event.timestamp,
                        final_event.event_type,
                        final_event.actor,
                        final_event.tenant_id,
                        final_event.tool_id,
                        final_event.outcome,
                        meta_str,
                        final_event.previous_event_hash,
                        final_event.event_hash,
                        final_event.session_id,
                        final_event.execution_id,
                        final_event.plan_fingerprint,
                        final_event.node_id,
                        final_event.worker_id,
                        final_event.fencing_token,
                        final_event.severity,
                    ),
                )
                return final_event

    async def get_events(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> Sequence[AuditEvent]:
        """Retrieve full ordered audit history filtered by execution_id and/or tenant_id."""
        with self._get_connection() as conn:
            if execution_id and tenant_id:
                rows = conn.execute(
                    "SELECT * FROM audit_events WHERE execution_id = ? AND tenant_id = ? ORDER BY sequence ASC",
                    (execution_id, tenant_id),
                ).fetchall()
            elif execution_id:
                rows = conn.execute(
                    "SELECT * FROM audit_events WHERE execution_id = ? ORDER BY sequence ASC",
                    (execution_id,),
                ).fetchall()
            elif tenant_id:
                rows = conn.execute(
                    "SELECT * FROM audit_events WHERE tenant_id = ? ORDER BY sequence ASC",
                    (tenant_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM audit_events ORDER BY sequence ASC").fetchall()
            return [self._row_to_event(r) for r in rows]

    async def get_event(self, event_id: str) -> AuditEvent | None:
        """Retrieve a specific audit event by event_id or id."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM audit_events WHERE id = ?", (event_id,)).fetchone()
            if not row:
                return None
            return self._row_to_event(row)

    async def get_latest_event(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> AuditEvent | None:
        """Retrieve the most recent audit event for an execution and/or tenant."""
        with self._get_connection() as conn:
            if execution_id and tenant_id:
                row = conn.execute(
                    "SELECT * FROM audit_events WHERE execution_id = ? AND tenant_id = ? ORDER BY sequence DESC LIMIT 1",
                    (execution_id, tenant_id),
                ).fetchone()
            elif execution_id:
                row = conn.execute(
                    "SELECT * FROM audit_events WHERE execution_id = ? ORDER BY sequence DESC LIMIT 1",
                    (execution_id,),
                ).fetchone()
            elif tenant_id:
                row = conn.execute(
                    "SELECT * FROM audit_events WHERE tenant_id = ? ORDER BY sequence DESC LIMIT 1",
                    (tenant_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()

            if not row:
                return None
            return self._row_to_event(row)

    async def verify_chain(
        self, execution_id: str | None = None, tenant_id: str | None = None
    ) -> AuditVerificationResult:
        """Verify sequence monotonicity, previous event hash linkages, and SHA-256 payload integrity."""
        events = await self.get_events(execution_id=execution_id, tenant_id=tenant_id)
        if not events:
            return AuditVerificationResult(
                valid=True,
                event_count=0,
                sequence_valid=True,
                hash_chain_valid=True,
                correlation_valid=True,
                terminal_state_valid=True,
                broken_at_sequence=None,
            )

        violations: list[str] = []
        seq_valid = True
        chain_valid = True
        corr_valid = True
        broken_seq: int | None = None

        expected_seq = events[0].sequence_number
        expected_prev_hash = events[0].previous_event_hash

        # If checking tenant chain or if execution starts from sequence 1:
        if tenant_id is not None or events[0].sequence_number == 1:
            expected_seq = 1
            expected_prev_hash = GENESIS_HASH

        first_sess = events[0].session_id
        first_fp = events[0].plan_fingerprint

        for ev in events:
            if ev.sequence_number != expected_seq:
                seq_valid = False
                if broken_seq is None:
                    broken_seq = ev.sequence_number
                violations.append(
                    f"Sequence gap/disorder at event {ev.event_id}: expected {expected_seq}, got {ev.sequence_number}"
                )

            if ev.previous_event_hash != expected_prev_hash:
                chain_valid = False
                if broken_seq is None:
                    broken_seq = ev.sequence_number
                violations.append(
                    f"Hash chain broken at sequence {ev.sequence_number}: expected prev {expected_prev_hash[:8]}, got {ev.previous_event_hash[:8]}"
                )

            # Verify payload SHA-256 hash match conforming to AuditEvent.__post_init__ canonical format
            canonical_payload = {
                "event_id": ev.event_id,
                "event_type": ev.event_type,
                "session_id": ev.session_id,
                "execution_id": ev.execution_id,
                "plan_fingerprint": ev.plan_fingerprint,
                "sequence_number": ev.sequence_number,
                "timestamp": ev.timestamp,
                "node_id": ev.node_id,
                "tool_id": ev.tool_id,
                "worker_id": ev.worker_id,
                "fencing_token": ev.fencing_token,
                "actor": ev.actor,
                "tenant_id": ev.tenant_id,
                "outcome": ev.outcome,
                "severity": ev.severity,
                "previous_event_hash": ev.previous_event_hash,
            }
            recalculated_hash = hashlib.sha256(
                json.dumps(canonical_payload, sort_keys=True).encode("utf-8")
            ).hexdigest()

            if recalculated_hash != ev.event_hash:
                chain_valid = False
                if broken_seq is None:
                    broken_seq = ev.sequence_number
                violations.append(
                    f"Payload tampered at sequence {ev.sequence_number}: calculated {recalculated_hash[:8]} != stored {ev.event_hash[:8]}"
                )

            if execution_id:
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
            broken_at_sequence=broken_seq if not is_valid else None,
        )

    async def startup_integrity_check(
        self, tenant_id: str | None = None
    ) -> AuditVerificationResult:
        """Perform startup integrity verification across all persistent audit log events."""
        with self._get_connection() as conn:
            if tenant_id:
                tenants = [tenant_id]
            else:
                rows = conn.execute("SELECT DISTINCT tenant_id FROM audit_events").fetchall()
                tenants = [r["tenant_id"] for r in rows]

        if not tenants:
            return AuditVerificationResult(
                valid=True,
                event_count=0,
                sequence_valid=True,
                hash_chain_valid=True,
                correlation_valid=True,
                terminal_state_valid=True,
                broken_at_sequence=None,
            )

        total_count = 0
        all_violations: list[str] = []
        is_all_valid = True
        broken_seq: int | None = None

        for t in tenants:
            res = await self.verify_chain(tenant_id=t)
            total_count += res.event_count
            if not res.valid:
                is_all_valid = False
                all_violations.extend([f"[Tenant {t}] {v}" for v in res.violations])
                if broken_seq is None and res.broken_at_sequence is not None:
                    broken_seq = res.broken_at_sequence

        return AuditVerificationResult(
            valid=is_all_valid,
            event_count=total_count,
            sequence_valid=is_all_valid,
            hash_chain_valid=is_all_valid,
            correlation_valid=is_all_valid,
            terminal_state_valid=True,
            violations=all_violations,
            broken_at_sequence=broken_seq,
        )

    def _row_to_event(self, row: sqlite3.Row) -> AuditEvent:
        row_keys = row.keys()
        meta_raw = row["metadata_json"] if "metadata_json" in row_keys else row["metadata"]
        meta = json.loads(meta_raw) if meta_raw else {}

        ev_id = row["id"] if "id" in row_keys else row["event_id"]
        seq = row["sequence"] if "sequence" in row_keys else row["sequence_number"]
        tool = (
            row["tool_name"]
            if "tool_name" in row_keys
            else (row["tool_id"] if "tool_id" in row_keys else None)
        )
        prev_h = row["previous_hash"] if "previous_hash" in row_keys else row["previous_event_hash"]
        t_id = row["tenant_id"] if "tenant_id" in row_keys else "default"
        actor = row["actor"] if "actor" in row_keys and row["actor"] else "anonymous"

        return AuditEvent(
            event_id=ev_id,
            event_type=row["event_type"],
            session_id=row["session_id"] if "session_id" in row_keys else "",
            execution_id=row["execution_id"] if "execution_id" in row_keys else "",
            plan_fingerprint=row["plan_fingerprint"] if "plan_fingerprint" in row_keys else "",
            sequence_number=seq,
            timestamp=row["timestamp"],
            node_id=row["node_id"] if "node_id" in row_keys else None,
            tool_id=tool,
            worker_id=row["worker_id"] if "worker_id" in row_keys else None,
            fencing_token=row["fencing_token"] if "fencing_token" in row_keys else None,
            actor=actor,
            tenant_id=t_id,
            outcome=row["outcome"],
            severity=row["severity"] if "severity" in row_keys else "INFO",
            previous_event_hash=prev_h,
            event_hash=row["event_hash"],
            metadata=meta,
        )
