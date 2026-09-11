"""Execution API Idempotency Store and State Machine.

Provides identity-scoped idempotency guarantees (tenant_id + user_id + idempotency_key),
SHA-256 payload fingerprinting, multi-state lifecycle management, automatic secret sanitization,
and both In-Memory and SQLite storage engines.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol

from nexusai.core.errors import (
    IdempotencyConflictError,
    IdempotencyError,
    IdempotencyLockedError,
    IdempotencyPayloadMismatchError,
)
from nexusai.infrastructure.observability.redaction import sanitize_secrets_recursive
from nexusai.logging.logger import logger

__all__ = [
    "IdempotencyState",
    "IdempotencyRecord",
    "IdempotencyStore",
    "InMemoryIdempotencyStore",
    "SqliteIdempotencyStore",
    "compute_payload_fingerprint",
    "classify_error_state",
    "IdempotencyError",
    "IdempotencyConflictError",
    "IdempotencyPayloadMismatchError",
    "IdempotencyLockedError",
]


class IdempotencyState(str, Enum):
    """Lifecycle states of an idempotent execution."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_TRANSIENT = "FAILED_TRANSIENT"  # Retryable (timeouts, network glitches)
    FAILED_TERMINAL = "FAILED_TERMINAL"  # Non-retryable (invalid input, security denial)
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


@dataclass
class IdempotencyRecord:
    """Identity-scoped idempotency record storing state, fingerprint, and cached results."""

    tenant_id: str
    user_id: str
    idempotency_key: str
    fingerprint: str
    state: IdempotencyState
    response: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 86400.0)

    @property
    def is_expired(self) -> bool:
        """Check if record has passed its TTL expiration timestamp."""
        return time.time() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary representation."""
        data = asdict(self)
        data["state"] = self.state.value
        return data


def compute_payload_fingerprint(payload: Any) -> str:
    """Compute a canonical SHA-256 fingerprint for request payload."""
    try:
        canonical_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except Exception as exc:
        raise ValueError(f"Failed to serialize payload for fingerprinting: {exc}") from exc
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def classify_error_state(err: Exception | str) -> IdempotencyState:
    """Classify execution error into FAILED_TRANSIENT (retryable) or FAILED_TERMINAL."""
    if isinstance(err, (TimeoutError, asyncio.TimeoutError)):
        return IdempotencyState.FAILED_TRANSIENT

    msg = str(err).lower()
    transient_keywords = (
        "timeout",
        "timed out",
        "transient",
        "temporary",
        "connection reset",
        "connection refused",
        "econnreset",
        "etimedout",
        "service unavailable",
        "503",
        "504",
        "retryable",
    )
    if any(keyword in msg for keyword in transient_keywords):
        return IdempotencyState.FAILED_TRANSIENT

    return IdempotencyState.FAILED_TERMINAL


class IdempotencyStore(Protocol):
    """Abstract protocol for identity-scoped idempotency storage backends."""

    async def start_execution(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        fingerprint: str,
        ttl_seconds: float = 86400.0,
    ) -> tuple[IdempotencyRecord, bool]:
        """Start or retrieve an execution record for the given scoped idempotency key.

        Returns:
            tuple[IdempotencyRecord, bool]:
                - (record, True): Execution registered or permitted to retry. Caller should execute.
                - (record, False): Execution completed or terminal error cached. Caller should replay.

        Raises:
            IdempotencyPayloadMismatchError: If the key was used with a different request payload.
            IdempotencyConflictError: If execution is already in progress (RUNNING or PENDING).
        """
        ...

    async def complete_execution(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        response: dict[str, Any],
    ) -> IdempotencyRecord:
        """Mark execution as SUCCEEDED, sanitizing and caching the output."""
        ...

    async def fail_execution(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        error: Exception | str,
        state: IdempotencyState | None = None,
    ) -> IdempotencyRecord:
        """Mark execution as failed with classified transient or terminal error state."""
        ...

    async def get(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
    ) -> IdempotencyRecord | None:
        """Retrieve record for tenant_id, user_id, and idempotency_key."""
        ...

    async def cleanup_expired(self) -> int:
        """Prune records whose TTL has expired, returning the count of removed records."""
        ...


class InMemoryIdempotencyStore:
    """Thread-safe and async-safe in-memory idempotency store for development/single-process."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], IdempotencyRecord] = {}
        self._lock = asyncio.Lock()

    async def start_execution(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        fingerprint: str,
        ttl_seconds: float = 86400.0,
    ) -> tuple[IdempotencyRecord, bool]:
        async with self._lock:
            key = (tenant_id, user_id, idempotency_key)
            record = self._records.get(key)
            now = time.time()

            # 1. Check if record exists and is still valid
            if record is not None:
                if record.is_expired:
                    # Treat expired record as clean slate
                    logger.debug(
                        f"Idempotency record expired for tenant={tenant_id}, user={user_id}, key={idempotency_key}"
                    )
                    record = None
                else:
                    # 2. Check for payload fingerprint mismatch
                    if record.fingerprint != fingerprint:
                        raise IdempotencyPayloadMismatchError(
                            f"Idempotency key '{idempotency_key}' payload mismatch: "
                            "the same key was previously invoked with different parameters."
                        )

                    # 3. Check execution state
                    if record.state in (IdempotencyState.RUNNING, IdempotencyState.PENDING):
                        raise IdempotencyConflictError(
                            f"Execution with idempotency key '{idempotency_key}' is currently in progress."
                        )

                    if record.state == IdempotencyState.SUCCEEDED:
                        return record, False

                    if record.state == IdempotencyState.FAILED_TERMINAL:
                        return record, False

                    if record.state in (
                        IdempotencyState.FAILED_TRANSIENT,
                        IdempotencyState.CANCELLED,
                    ):
                        # Retryable: transition back to RUNNING
                        record.state = IdempotencyState.RUNNING
                        record.updated_at = now
                        record.error_message = None
                        return record, True

            # 4. Insert new record in RUNNING state
            new_record = IdempotencyRecord(
                tenant_id=tenant_id,
                user_id=user_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                state=IdempotencyState.RUNNING,
                created_at=now,
                updated_at=now,
                expires_at=now + ttl_seconds,
            )
            self._records[key] = new_record
            return new_record, True

    async def complete_execution(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        response: dict[str, Any],
    ) -> IdempotencyRecord:
        sanitized_response = sanitize_secrets_recursive(response)
        async with self._lock:
            key = (tenant_id, user_id, idempotency_key)
            record = self._records.get(key)
            now = time.time()
            if record is None:
                record = IdempotencyRecord(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    fingerprint="",
                    state=IdempotencyState.SUCCEEDED,
                    response=sanitized_response,
                    created_at=now,
                    updated_at=now,
                )
                self._records[key] = record
            else:
                record.state = IdempotencyState.SUCCEEDED
                record.response = sanitized_response
                record.error_message = None
                record.updated_at = now
            return record

    async def fail_execution(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        error: Exception | str,
        state: IdempotencyState | None = None,
    ) -> IdempotencyRecord:
        resolved_state = state or classify_error_state(error)
        err_msg = str(error)
        async with self._lock:
            key = (tenant_id, user_id, idempotency_key)
            record = self._records.get(key)
            now = time.time()
            if record is None:
                record = IdempotencyRecord(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    fingerprint="",
                    state=resolved_state,
                    error_message=err_msg,
                    created_at=now,
                    updated_at=now,
                )
                self._records[key] = record
            else:
                record.state = resolved_state
                record.error_message = err_msg
                record.updated_at = now
            return record

    async def get(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
    ) -> IdempotencyRecord | None:
        async with self._lock:
            key = (tenant_id, user_id, idempotency_key)
            record = self._records.get(key)
            if record and record.is_expired:
                return None
            return record

    async def cleanup_expired(self) -> int:
        async with self._lock:
            now = time.time()
            expired_keys = [k for k, v in self._records.items() if now >= v.expires_at]
            for k in expired_keys:
                del self._records[k]
            return len(expired_keys)


class SqliteIdempotencyStore:
    """Durable SQLite idempotency store with WAL mode and unique constraint enforcement."""

    def __init__(self, db_path: str = ":memory:") -> None:
        if db_path == ":memory:":
            self._is_memory = True
            self._db_uri = f"file:memdb_idem_{id(self)}_{time.time_ns()}?mode=memory&cache=shared"
            self._keepalive: sqlite3.Connection | None = sqlite3.connect(
                self._db_uri, uri=True, check_same_thread=False
            )
            self.db_path = self._db_uri
        else:
            self._is_memory = False
            self._keepalive = None
            self.db_path = db_path

        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0, uri=self._is_memory)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_records (
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    state TEXT NOT NULL,
                    response_json TEXT,
                    error_message TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    PRIMARY KEY (tenant_id, user_id, idempotency_key)
                );
                """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_idempotency_expires_at
                ON idempotency_records (expires_at);
                """)
            conn.commit()

    async def start_execution(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        fingerprint: str,
        ttl_seconds: float = 86400.0,
    ) -> tuple[IdempotencyRecord, bool]:
        return await asyncio.to_thread(
            self._start_execution_sync,
            tenant_id,
            user_id,
            idempotency_key,
            fingerprint,
            ttl_seconds,
        )

    def _start_execution_sync(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        fingerprint: str,
        ttl_seconds: float,
    ) -> tuple[IdempotencyRecord, bool]:
        now = time.time()
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT tenant_id, user_id, idempotency_key, fingerprint, state,
                           response_json, error_message, created_at, updated_at, expires_at
                    FROM idempotency_records
                    WHERE tenant_id = ? AND user_id = ? AND idempotency_key = ?
                    """,
                    (tenant_id, user_id, idempotency_key),
                )
                row = cursor.fetchone()

                if row is not None:
                    record = self._row_to_record(row)
                    if record.is_expired:
                        conn.execute(
                            """
                            UPDATE idempotency_records
                            SET fingerprint = ?, state = ?, response_json = NULL,
                                error_message = NULL, created_at = ?, updated_at = ?, expires_at = ?
                            WHERE tenant_id = ? AND user_id = ? AND idempotency_key = ?
                            """,
                            (
                                fingerprint,
                                IdempotencyState.RUNNING.value,
                                now,
                                now,
                                now + ttl_seconds,
                                tenant_id,
                                user_id,
                                idempotency_key,
                            ),
                        )
                        conn.commit()
                        record.fingerprint = fingerprint
                        record.state = IdempotencyState.RUNNING
                        record.response = None
                        record.error_message = None
                        record.created_at = now
                        record.updated_at = now
                        record.expires_at = now + ttl_seconds
                        return record, True

                    if record.fingerprint != fingerprint:
                        raise IdempotencyPayloadMismatchError(
                            f"Idempotency key '{idempotency_key}' payload mismatch: "
                            "the same key was previously invoked with different parameters."
                        )

                    if record.state in (IdempotencyState.RUNNING, IdempotencyState.PENDING):
                        raise IdempotencyConflictError(
                            f"Execution with idempotency key '{idempotency_key}' is currently in progress."
                        )

                    if record.state == IdempotencyState.SUCCEEDED:
                        return record, False

                    if record.state == IdempotencyState.FAILED_TERMINAL:
                        return record, False

                    if record.state in (
                        IdempotencyState.FAILED_TRANSIENT,
                        IdempotencyState.CANCELLED,
                    ):
                        conn.execute(
                            """
                            UPDATE idempotency_records
                            SET state = ?, updated_at = ?, error_message = NULL
                            WHERE tenant_id = ? AND user_id = ? AND idempotency_key = ?
                            """,
                            (
                                IdempotencyState.RUNNING.value,
                                now,
                                tenant_id,
                                user_id,
                                idempotency_key,
                            ),
                        )
                        conn.commit()
                        record.state = IdempotencyState.RUNNING
                        record.updated_at = now
                        record.error_message = None
                        return record, True

                expires_at = now + ttl_seconds
                try:
                    conn.execute(
                        """
                        INSERT INTO idempotency_records (
                            tenant_id, user_id, idempotency_key, fingerprint, state,
                            response_json, error_message, created_at, updated_at, expires_at
                        ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
                        """,
                        (
                            tenant_id,
                            user_id,
                            idempotency_key,
                            fingerprint,
                            IdempotencyState.RUNNING.value,
                            now,
                            now,
                            expires_at,
                        ),
                    )
                    conn.commit()
                except sqlite3.IntegrityError:
                    raise IdempotencyConflictError(
                        f"Execution with idempotency key '{idempotency_key}' is currently in progress."
                    )
                return (
                    IdempotencyRecord(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        idempotency_key=idempotency_key,
                        fingerprint=fingerprint,
                        state=IdempotencyState.RUNNING,
                        created_at=now,
                        updated_at=now,
                        expires_at=expires_at,
                    ),
                    True,
                )
            new_record = IdempotencyRecord(
                tenant_id=tenant_id,
                user_id=user_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                state=IdempotencyState.RUNNING,
                created_at=now,
                updated_at=now,
                expires_at=expires_at,
            )
            return new_record, True

    async def complete_execution(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        response: dict[str, Any],
    ) -> IdempotencyRecord:
        sanitized_response = sanitize_secrets_recursive(response)
        return await asyncio.to_thread(
            self._complete_execution_sync,
            tenant_id,
            user_id,
            idempotency_key,
            sanitized_response,
        )

    def _complete_execution_sync(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        sanitized_response: dict[str, Any],
    ) -> IdempotencyRecord:
        now = time.time()
        resp_json = json.dumps(sanitized_response)
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE idempotency_records
                    SET state = ?, response_json = ?, error_message = NULL, updated_at = ?
                    WHERE tenant_id = ? AND user_id = ? AND idempotency_key = ?
                    """,
                    (
                        IdempotencyState.SUCCEEDED.value,
                        resp_json,
                        now,
                        tenant_id,
                        user_id,
                        idempotency_key,
                    ),
                )
                conn.commit()

                cursor = conn.execute(
                    """
                    SELECT tenant_id, user_id, idempotency_key, fingerprint, state,
                           response_json, error_message, created_at, updated_at, expires_at
                    FROM idempotency_records
                    WHERE tenant_id = ? AND user_id = ? AND idempotency_key = ?
                    """,
                    (tenant_id, user_id, idempotency_key),
                )
                row = cursor.fetchone()
                if row is not None:
                    return self._row_to_record(row)

                return IdempotencyRecord(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    fingerprint="",
                    state=IdempotencyState.SUCCEEDED,
                    response=sanitized_response,
                    created_at=now,
                    updated_at=now,
                )

    async def fail_execution(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        error: Exception | str,
        state: IdempotencyState | None = None,
    ) -> IdempotencyRecord:
        resolved_state = state or classify_error_state(error)
        err_msg = str(error)
        return await asyncio.to_thread(
            self._fail_execution_sync,
            tenant_id,
            user_id,
            idempotency_key,
            err_msg,
            resolved_state,
        )

    def _fail_execution_sync(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        err_msg: str,
        resolved_state: IdempotencyState,
    ) -> IdempotencyRecord:
        now = time.time()
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE idempotency_records
                    SET state = ?, error_message = ?, updated_at = ?
                    WHERE tenant_id = ? AND user_id = ? AND idempotency_key = ?
                    """,
                    (
                        resolved_state.value,
                        err_msg,
                        now,
                        tenant_id,
                        user_id,
                        idempotency_key,
                    ),
                )
                conn.commit()

                cursor = conn.execute(
                    """
                    SELECT tenant_id, user_id, idempotency_key, fingerprint, state,
                           response_json, error_message, created_at, updated_at, expires_at
                    FROM idempotency_records
                    WHERE tenant_id = ? AND user_id = ? AND idempotency_key = ?
                    """,
                    (tenant_id, user_id, idempotency_key),
                )
                row = cursor.fetchone()
                if row is not None:
                    return self._row_to_record(row)

                return IdempotencyRecord(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    fingerprint="",
                    state=resolved_state,
                    error_message=err_msg,
                    created_at=now,
                    updated_at=now,
                )

    async def get(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
    ) -> IdempotencyRecord | None:
        return await asyncio.to_thread(self._get_sync, tenant_id, user_id, idempotency_key)

    def _get_sync(
        self,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
    ) -> IdempotencyRecord | None:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT tenant_id, user_id, idempotency_key, fingerprint, state,
                           response_json, error_message, created_at, updated_at, expires_at
                    FROM idempotency_records
                    WHERE tenant_id = ? AND user_id = ? AND idempotency_key = ?
                    """,
                    (tenant_id, user_id, idempotency_key),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                record = self._row_to_record(row)
                if record.is_expired:
                    return None
                return record

    async def cleanup_expired(self) -> int:
        return await asyncio.to_thread(self._cleanup_expired_sync)

    def _cleanup_expired_sync(self) -> int:
        now = time.time()
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM idempotency_records WHERE expires_at <= ?",
                    (now,),
                )
                deleted_count = cursor.rowcount
                conn.commit()
                return deleted_count

    def _row_to_record(self, row: sqlite3.Row) -> IdempotencyRecord:
        resp = json.loads(row["response_json"]) if row["response_json"] else None
        return IdempotencyRecord(
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            idempotency_key=row["idempotency_key"],
            fingerprint=row["fingerprint"],
            state=IdempotencyState(row["state"]),
            response=resp,
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
        )
