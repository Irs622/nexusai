"""
SQLiteMemoryStore storage implementation storing serialized aggregate payloads.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

from nexusai.memory.contracts.storage import MemoryStorage
from nexusai.memory.domain.record import MemoryRecord
from nexusai.memory.serializer import JSONMemorySerializer, MemorySerializer


class SQLiteMemoryStore(MemoryStorage):
    """SQLite persistence storage engine storing serialized aggregate payloads."""

    def __init__(
        self, db_path: str | Path = ":memory:", serializer: MemorySerializer | None = None
    ) -> None:
        self._db_path = str(db_path)
        self._serializer = serializer or JSONMemorySerializer()
        self._memory_conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._db_path == ":memory:":
            if not hasattr(self, "_memory_conn") or self._memory_conn is None:
                self._memory_conn = sqlite3.connect(":memory:")
                self._memory_conn.row_factory = sqlite3.Row
            return self._memory_conn
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_records (
                    id TEXT PRIMARY KEY,
                    payload_bytes BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    async def save(self, record: MemoryRecord) -> None:
        """Save MemoryRecord aggregate to SQLite as serialized payload."""
        payload_bytes = self._serializer.serialize(record)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_records (
                    id, payload_bytes, created_at, updated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    record.id,
                    payload_bytes,
                    record.metadata.created_at,
                    record.metadata.updated_at,
                ),
            )
            conn.commit()

    async def get(self, record_id: str) -> MemoryRecord | None:
        """Get MemoryRecord from SQLite payload_bytes."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT payload_bytes FROM memory_records WHERE id = ?", (record_id,)
            ).fetchone()

        if not row:
            return None

        return self._serializer.deserialize(row["payload_bytes"])

    async def delete(self, record_id: str) -> bool:
        """Delete MemoryRecord from SQLite."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM memory_records WHERE id = ?", (record_id,))
            conn.commit()
            return cursor.rowcount > 0

    async def list_records(self, limit: int = 100) -> Sequence[MemoryRecord]:
        """List stored MemoryRecords up to limit."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT payload_bytes FROM memory_records ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        records: list[MemoryRecord] = []
        for row in rows:
            try:
                records.append(self._serializer.deserialize(row["payload_bytes"]))
            except Exception:
                continue
        return records
