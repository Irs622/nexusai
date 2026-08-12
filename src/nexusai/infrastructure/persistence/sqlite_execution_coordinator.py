"""SQLite implementation of IExecutionCoordinator with WAL mode, atomic Compare-And-Set (CAS) leases, and fencing tokens."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from nexusai.brain.domain.execution_coordination import (
    ExecutionLease,
    FencingTokenError,
    LeaseAcquisitionError,
    LeaseStatus,
    StaleWorkerError,
    WorkerIdentity,
)
from nexusai.brain.ports.execution_coordinator_port import IExecutionCoordinator


class SQLiteExecutionCoordinator(IExecutionCoordinator):
    """Durable multi-process SQLite execution lease coordinator with Compare-And-Set transaction boundaries."""

    def __init__(self, db_path: str = ":memory:", busy_timeout_ms: int = 10000) -> None:
        self._keepalive: sqlite3.Connection | None
        if db_path == ":memory:":
            self.db_path = "file:mem_coord?mode=memory&cache=shared"
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
                CREATE TABLE IF NOT EXISTS execution_leases (
                    lease_id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    fencing_token INTEGER NOT NULL,
                    acquired_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    audit_hash TEXT NOT NULL,
                    metadata TEXT NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lease_session ON execution_leases(session_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lease_worker ON execution_leases(worker_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lease_status ON execution_leases(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lease_expires ON execution_leases(expires_at);")

    async def acquire_execution_lease(
        self,
        execution_id: str,
        session_id: str,
        worker: WorkerIdentity,
        ttl_seconds: float = 30.0,
    ) -> ExecutionLease:
        """Atomically acquire time-bounded execution lease and issue monotonically increasing fencing token."""
        now = time.time()
        expires = now + ttl_seconds

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM execution_leases WHERE execution_id = ?", (execution_id,)).fetchone()
            if row:
                st = LeaseStatus(row["status"])
                # Active non-expired lease held by another worker -> MUST FAIL!
                if st in (LeaseStatus.LEASED, LeaseStatus.RENEWED) and now < row["expires_at"] and row["worker_id"] != worker.worker_id:
                    raise LeaseAcquisitionError(f"Execution '{execution_id}' is already leased by worker '{row['worker_id']}'")

                # Re-acquiring or takeover expired lease -> Monotonically increment fencing token
                next_token = row["fencing_token"] + 1
                lease_id = f"lease-{execution_id}-{next_token}"
                meta_str = json.dumps({"worker": worker.worker_id, "pid": worker.process_id})

                cursor = conn.execute(
                    """
                    UPDATE execution_leases
                    SET lease_id = ?, worker_id = ?, fencing_token = ?, acquired_at = ?, expires_at = ?, status = ?, metadata = ?
                    WHERE execution_id = ? AND (expires_at <= ? OR worker_id = ? OR status IN (?, ?))
                    """,
                    (
                        lease_id,
                        worker.worker_id,
                        next_token,
                        now,
                        expires,
                        LeaseStatus.LEASED.value,
                        meta_str,
                        execution_id,
                        now,
                        worker.worker_id,
                        LeaseStatus.RELEASED.value,
                        LeaseStatus.EXPIRED.value,
                    ),
                )
                if cursor.rowcount == 0:
                    raise LeaseAcquisitionError(f"Atomic compare-and-set lease acquisition failed for '{execution_id}'")

                return ExecutionLease(
                    lease_id=lease_id,
                    execution_id=execution_id,
                    session_id=session_id,
                    worker_id=worker.worker_id,
                    fencing_token=next_token,
                    acquired_at=now,
                    expires_at=expires,
                    status=LeaseStatus.LEASED,
                )
            else:
                # First time creation
                lease_id = f"lease-{execution_id}-1"
                meta_str = json.dumps({"worker": worker.worker_id, "pid": worker.process_id})
                try:
                    conn.execute(
                        """
                        INSERT INTO execution_leases (
                            lease_id, execution_id, session_id, worker_id, fencing_token,
                            acquired_at, expires_at, status, audit_hash, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            lease_id,
                            execution_id,
                            session_id,
                            worker.worker_id,
                            1,
                            now,
                            expires,
                            LeaseStatus.LEASED.value,
                            "hash-init",
                            meta_str,
                        ),
                    )
                except sqlite3.IntegrityError:
                    raise LeaseAcquisitionError(f"Race condition detected during initial lease creation for '{execution_id}'")

                return ExecutionLease(
                    lease_id=lease_id,
                    execution_id=execution_id,
                    session_id=session_id,
                    worker_id=worker.worker_id,
                    fencing_token=1,
                    acquired_at=now,
                    expires_at=expires,
                    status=LeaseStatus.LEASED,
                )

    async def renew_execution_lease(
        self,
        lease_id: str,
        worker: WorkerIdentity,
        ttl_seconds: float = 30.0,
    ) -> ExecutionLease:
        """Atomically extend lease TTL for current owner."""
        now = time.time()
        expires = now + ttl_seconds

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM execution_leases WHERE lease_id = ?", (lease_id,)).fetchone()
            if not row:
                raise StaleWorkerError(f"Lease '{lease_id}' not found")

            if row["worker_id"] != worker.worker_id:
                raise StaleWorkerError(f"Worker '{worker.worker_id}' cannot renew lease owned by '{row['worker_id']}'")

            if now >= row["expires_at"]:
                raise StaleWorkerError(f"Lease '{lease_id}' has already expired and cannot be renewed")

            cursor = conn.execute(
                """
                UPDATE execution_leases
                SET expires_at = ?, status = ?
                WHERE lease_id = ? AND worker_id = ? AND expires_at > ?
                """,
                (expires, LeaseStatus.RENEWED.value, lease_id, worker.worker_id, now),
            )

            if cursor.rowcount == 0:
                raise StaleWorkerError(f"Atomic compare-and-set lease renewal failed for '{lease_id}'")

            return ExecutionLease(
                lease_id=lease_id,
                execution_id=row["execution_id"],
                session_id=row["session_id"],
                worker_id=worker.worker_id,
                fencing_token=row["fencing_token"],
                acquired_at=row["acquired_at"],
                expires_at=expires,
                status=LeaseStatus.RENEWED,
            )

    async def release_execution_lease(
        self,
        lease_id: str,
        worker: WorkerIdentity,
    ) -> bool:
        """Atomically release lease ownership."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM execution_leases WHERE lease_id = ?", (lease_id,)).fetchone()
            if not row:
                return False

            if row["worker_id"] != worker.worker_id:
                raise StaleWorkerError(f"Worker '{worker.worker_id}' cannot release lease owned by '{row['worker_id']}'")

            cursor = conn.execute(
                "UPDATE execution_leases SET status = ? WHERE lease_id = ? AND worker_id = ?",
                (LeaseStatus.RELEASED.value, lease_id, worker.worker_id),
            )
            return cursor.rowcount > 0

    async def get_current_lease(self, execution_id: str) -> ExecutionLease | None:
        """Retrieve current lease status for execution_id."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM execution_leases WHERE execution_id = ?", (execution_id,)).fetchone()
            if not row:
                return None

            st = LeaseStatus(row["status"])
            now = time.time()
            if st in (LeaseStatus.LEASED, LeaseStatus.RENEWED) and now >= row["expires_at"]:
                st = LeaseStatus.EXPIRED

            return ExecutionLease(
                lease_id=row["lease_id"],
                execution_id=row["execution_id"],
                session_id=row["session_id"],
                worker_id=row["worker_id"],
                fencing_token=row["fencing_token"],
                acquired_at=row["acquired_at"],
                expires_at=row["expires_at"],
                status=st,
            )

    async def validate_lease_and_fencing_token(
        self,
        execution_id: str,
        worker_id: str,
        expected_token: int,
    ) -> bool:
        """Verify worker identity and monotonically increasing fencing token validity prior to side-effect execution."""
        now = time.time()

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM execution_leases WHERE execution_id = ?", (execution_id,)).fetchone()
            if not row:
                raise FencingTokenError(f"No lease found for execution '{execution_id}'")

            if row["worker_id"] != worker_id:
                raise StaleWorkerError(f"Stale worker execution attempt: lease owned by '{row['worker_id']}', caller is '{worker_id}'")

            if now >= row["expires_at"]:
                raise FencingTokenError(f"Lease for execution '{execution_id}' expired at {row['expires_at']}")

            # Fencing token invariant (P4-6-INV-08 & INV-09)
            if expected_token < row["fencing_token"]:
                raise FencingTokenError(f"Obsolete fencing token {expected_token} < active token {row['fencing_token']}")

            return True

    async def recover_expired_execution_lease(
        self,
        execution_id: str,
        new_worker: WorkerIdentity,
        ttl_seconds: float = 30.0,
    ) -> ExecutionLease:
        """Atomically takeover an expired lease, issue a higher fencing token, and assign to new_worker."""
        now = time.time()

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM execution_leases WHERE execution_id = ?", (execution_id,)).fetchone()
            if not row:
                raise LeaseAcquisitionError(f"Execution lease '{execution_id}' not found for recovery")

            if now < row["expires_at"] and row["status"] in (LeaseStatus.LEASED.value, LeaseStatus.RENEWED.value):
                raise LeaseAcquisitionError(f"Cannot recover lease for execution '{execution_id}': active lease held by worker '{row['worker_id']}'")

            next_token = row["fencing_token"] + 1
            lease_id = f"lease-{execution_id}-{next_token}"
            expires = now + ttl_seconds

            cursor = conn.execute(
                """
                UPDATE execution_leases
                SET lease_id = ?, worker_id = ?, fencing_token = ?, acquired_at = ?, expires_at = ?, status = ?
                WHERE execution_id = ? AND (expires_at <= ? OR status IN (?, ?))
                """,
                (lease_id, new_worker.worker_id, next_token, now, expires, LeaseStatus.LEASED.value, execution_id, now, LeaseStatus.RELEASED.value, LeaseStatus.EXPIRED.value),
            )

            if cursor.rowcount == 0:
                raise LeaseAcquisitionError(f"Atomic compare-and-set lease takeover failed for execution '{execution_id}'")

            return ExecutionLease(
                lease_id=lease_id,
                execution_id=execution_id,
                session_id=row["session_id"],
                worker_id=new_worker.worker_id,
                fencing_token=next_token,
                acquired_at=now,
                expires_at=expires,
                status=LeaseStatus.LEASED,
            )
