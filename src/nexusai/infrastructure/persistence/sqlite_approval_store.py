"""SQLite implementation of IApprovalStore with WAL mode, atomic state transitions, and single-use grant replay protection."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any
from uuid import uuid4

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalCancelledError,
    ApprovalError,
    ApprovalExpiredError,
    ApprovalGrant,
    ApprovalMismatchError,
    ApprovalReplayError,
    ApprovalStatus,
    HumanApprovalDecision,
    HumanApprovalRequest,
    RiskLevel,
)
from nexusai.brain.ports.approval_store_port import IApprovalStore


class SQLiteApprovalStore(IApprovalStore):
    """Durable SQLite storage for Human Approval requests, decisions, and single-use grants."""

    def __init__(self, db_path: str = ":memory:", busy_timeout_ms: int = 10000) -> None:
        self._keepalive: sqlite3.Connection | None
        if db_path == ":memory:":
            self.db_path = f"file:mem_app_{uuid4().hex}?mode=memory&cache=shared"
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
                CREATE TABLE IF NOT EXISTS approval_requests (
                    approval_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    plan_fingerprint TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    tool_id TEXT NOT NULL,
                    tool_version TEXT NOT NULL,
                    requested_capabilities TEXT NOT NULL,
                    resource_scope TEXT NOT NULL,
                    action_digest TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    prompt_summary TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    actor TEXT,
                    reason TEXT,
                    decided_at REAL,
                    audit_hash TEXT,
                    consumed_at REAL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_approval_session ON approval_requests(session_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_approval_execution ON approval_requests(execution_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_approval_status ON approval_requests(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_approval_expires ON approval_requests(expires_at);")

    async def save_request(self, request: HumanApprovalRequest) -> HumanApprovalRequest:
        """Persist a new safety approval request in PENDING status."""
        caps_str = json.dumps([c.value for c in request.binding.requested_capabilities])
        now = time.time()
        expires = request.expires_at or (now + 600.0)

        with self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO approval_requests (
                        approval_id, session_id, execution_id, plan_fingerprint, node_id,
                        tool_id, tool_version, requested_capabilities, resource_scope, action_digest,
                        risk_level, prompt_summary, status, created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.approval_id,
                        request.binding.session_id,
                        request.binding.execution_id,
                        request.binding.plan_fingerprint,
                        request.binding.node_id,
                        request.binding.tool_id,
                        request.binding.tool_version,
                        caps_str,
                        request.binding.resource_scope,
                        request.binding.action_digest,
                        request.risk_level.value,
                        request.prompt_summary,
                        ApprovalStatus.PENDING.value,
                        request.created_at,
                        expires,
                    ),
                )
            except sqlite3.IntegrityError:
                raise ValueError(f"Approval request '{request.approval_id}' already exists in store")

        return request

    async def get_request(self, approval_id: str) -> HumanApprovalRequest | None:
        """Retrieve approval request state by approval_id."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM approval_requests WHERE approval_id = ?", (approval_id,)).fetchone()
            if not row:
                return None

            caps_list = json.loads(row["requested_capabilities"])
            caps = frozenset({ToolCapability(c) for c in caps_list})

            binding = ActionBinding(
                session_id=row["session_id"],
                execution_id=row["execution_id"],
                plan_fingerprint=row["plan_fingerprint"],
                node_id=row["node_id"],
                tool_id=row["tool_id"],
                tool_version=row["tool_version"],
                requested_capabilities=caps,
                resource_scope=row["resource_scope"],
                action_digest=row["action_digest"],
            )

            status = ApprovalStatus(row["status"])
            now = time.time()
            if status == ApprovalStatus.PENDING and now >= row["expires_at"]:
                status = ApprovalStatus.EXPIRED

            return HumanApprovalRequest(
                approval_id=row["approval_id"],
                binding=binding,
                risk_level=RiskLevel(row["risk_level"]),
                prompt_summary=row["prompt_summary"],
                status=status,
                created_at=row["created_at"],
                expires_at=row["expires_at"],
            )

    async def record_decision(self, decision: HumanApprovalDecision) -> ApprovalGrant:
        """Atomically record operator decision. Returns single-use ApprovalGrant if APPROVED."""
        now = time.time()

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM approval_requests WHERE approval_id = ?", (decision.approval_id,)).fetchone()
            if not row:
                raise ValueError(f"Approval request '{decision.approval_id}' not found in store")

            if row["status"] != ApprovalStatus.PENDING.value:
                raise ValueError(f"Cannot submit decision for request '{decision.approval_id}' in status '{row['status']}'")

            if now >= row["expires_at"]:
                conn.execute("UPDATE approval_requests SET status = ? WHERE approval_id = ?", (ApprovalStatus.EXPIRED.value, decision.approval_id))
                raise ApprovalExpiredError(f"Approval request '{decision.approval_id}' has expired")

            if decision.status == ApprovalStatus.DENIED:
                conn.execute(
                    "UPDATE approval_requests SET status = ?, actor = ?, reason = ?, decided_at = ? WHERE approval_id = ?",
                    (ApprovalStatus.DENIED.value, decision.actor, decision.reason, now, decision.approval_id),
                )
                raise ApprovalMismatchError(f"Human operator denied request '{decision.approval_id}': {decision.reason}")

            # APPROVED -> Record grant and audit hash
            caps_list = json.loads(row["requested_capabilities"])
            caps = frozenset({ToolCapability(c) for c in caps_list})
            binding = ActionBinding(
                session_id=row["session_id"],
                execution_id=row["execution_id"],
                plan_fingerprint=row["plan_fingerprint"],
                node_id=row["node_id"],
                tool_id=row["tool_id"],
                tool_version=row["tool_version"],
                requested_capabilities=caps,
                resource_scope=row["resource_scope"],
                action_digest=row["action_digest"],
            )

            grant_id = f"grant-{decision.approval_id}"
            grant = ApprovalGrant(
                grant_id=grant_id,
                approval_id=decision.approval_id,
                binding=binding,
                issued_at=now,
                expires_at=row["expires_at"],
                actor=decision.actor,
            )

            cursor = conn.execute(
                """
                UPDATE approval_requests
                SET status = ?, actor = ?, reason = ?, decided_at = ?, audit_hash = ?
                WHERE approval_id = ? AND status = ?
                """,
                (ApprovalStatus.APPROVED.value, decision.actor, decision.reason, now, grant.audit_hash, decision.approval_id, ApprovalStatus.PENDING.value),
            )

            if cursor.rowcount == 0:
                raise ValueError(f"Atomic decision transition failed for request '{decision.approval_id}'")

            return grant

    async def get_grant(self, grant_id: str) -> ApprovalGrant | None:
        """Retrieve approval grant state by grant_id."""
        approval_id = grant_id.replace("grant-", "")
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM approval_requests WHERE approval_id = ?", (approval_id,)).fetchone()
            if not row or row["status"] not in (ApprovalStatus.APPROVED.value, ApprovalStatus.CONSUMED.value):
                return None

            caps_list = json.loads(row["requested_capabilities"])
            caps = frozenset({ToolCapability(c) for c in caps_list})
            binding = ActionBinding(
                session_id=row["session_id"],
                execution_id=row["execution_id"],
                plan_fingerprint=row["plan_fingerprint"],
                node_id=row["node_id"],
                tool_id=row["tool_id"],
                tool_version=row["tool_version"],
                requested_capabilities=caps,
                resource_scope=row["resource_scope"],
                action_digest=row["action_digest"],
            )

            return ApprovalGrant(
                grant_id=grant_id,
                approval_id=approval_id,
                binding=binding,
                issued_at=row["decided_at"] or row["created_at"],
                expires_at=row["expires_at"],
                actor=row["actor"] or "operator",
                consumed_at=row["consumed_at"],
                audit_hash=row["audit_hash"] or "",
            )

    async def verify_and_consume_grant(self, grant_id: str, expected_binding: ActionBinding) -> bool:
        """Atomically verify binding digest, expiration, and consume single-use grant in durable store."""
        approval_id = grant_id.replace("grant-", "")
        now = time.time()

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM approval_requests WHERE approval_id = ?", (approval_id,)).fetchone()
            if not row:
                raise ApprovalMismatchError(f"Approval grant '{grant_id}' not found in durable store")

            if row["consumed_at"] is not None or row["status"] == ApprovalStatus.CONSUMED.value:
                raise ApprovalReplayError(f"Approval grant '{grant_id}' has already been consumed at {row['consumed_at']}")

            if now >= row["expires_at"]:
                raise ApprovalExpiredError(f"Approval grant '{grant_id}' has expired")

            if row["action_digest"] != expected_binding.action_digest:
                raise ApprovalMismatchError(
                    f"Action binding mismatch: persisted digest '{row['action_digest']}' != expected '{expected_binding.action_digest}'"
                )

            # Atomic single-use consumption SQL update
            cursor = conn.execute(
                """
                UPDATE approval_requests
                SET status = ?, consumed_at = ?
                WHERE approval_id = ? AND status = ? AND consumed_at IS NULL
                """,
                (ApprovalStatus.CONSUMED.value, now, approval_id, ApprovalStatus.APPROVED.value),
            )

            if cursor.rowcount == 0:
                raise ApprovalReplayError(f"Approval grant '{grant_id}' single-use consumption failed (already consumed or non-approved status)")

            return True

    async def cancel_execution_requests(self, execution_id: str) -> int:
        """Cancel all pending requests bound to execution_id across processes."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE approval_requests SET status = ? WHERE execution_id = ? AND status = ?",
                (ApprovalStatus.CANCELLED.value, execution_id, ApprovalStatus.PENDING.value),
            )
            return cursor.rowcount
