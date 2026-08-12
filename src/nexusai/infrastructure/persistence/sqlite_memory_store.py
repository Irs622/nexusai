"""SQLite implementation of IMemoryStore with WAL mode, strict SQL session isolation, and provenance persistence."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from typing import Any

from nexusai.brain.domain.memory import (
    MemoryEntry,
    MemoryProvenance,
    MemoryType,
    PrivacyLevel,
)
from nexusai.brain.ports.memory_port import IMemoryStore
from nexusai.brain.ports.observability_port import IObservabilityPort


class SQLiteMemoryStore(IMemoryStore):
    """Durable SQLite memory storage engine enforcing strict SQL session isolation and provenance tracking."""

    def __init__(
        self,
        db_path: str = ":memory:",
        telemetry: IObservabilityPort | None = None,
    ) -> None:
        self.db_path = db_path
        self.telemetry = telemetry
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and configure thread-local SQLite connection with WAL mode."""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        """Initialize memories schema with indexes."""
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        memory_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        execution_id TEXT,
                        memory_type TEXT NOT NULL,
                        content TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        source_id TEXT,
                        confidence REAL NOT NULL,
                        version INTEGER NOT NULL,
                        invalidated INTEGER NOT NULL,
                        privacy_level TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL,
                        metadata_json TEXT
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_memories_session_type
                    ON memories (session_id, memory_type)
                """)
        finally:
            conn.close()

    async def store(self, entry: MemoryEntry) -> None:
        """Store a memory entry with session isolation and provenance persistence."""
        await asyncio.to_thread(self._sync_store, entry)

    def _sync_store(self, entry: MemoryEntry) -> None:
        conn = self._get_connection()
        try:
            meta_json = json.dumps(dict(entry.metadata))
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO memories (
                        memory_id, session_id, execution_id, memory_type, content,
                        source_type, source_id, confidence, version, invalidated,
                        privacy_level, created_at, expires_at, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.memory_id,
                        entry.session_id,
                        entry.execution_id,
                        entry.memory_type.value,
                        entry.content,
                        entry.provenance.source_type,
                        entry.provenance.source_id,
                        entry.provenance.confidence,
                        entry.provenance.version,
                        1 if entry.provenance.invalidated else 0,
                        entry.privacy_level.value,
                        entry.created_at,
                        entry.expires_at,
                        meta_json,
                    ),
                )
        finally:
            conn.close()

    async def load(self, memory_id: str, session_id: str) -> MemoryEntry | None:
        """Load a memory entry enforcing strict SQL session isolation (WHERE session_id = ?)."""
        return await asyncio.to_thread(self._sync_load, memory_id, session_id)

    def _sync_load(self, memory_id: str, session_id: str) -> MemoryEntry | None:
        conn = self._get_connection()
        try:
            row = conn.execute(
                """
                SELECT * FROM memories
                WHERE memory_id = ? AND session_id = ?
                """,
                (memory_id, session_id),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_entry(row)
        finally:
            conn.close()

    async def list_session_memories(
        self,
        session_id: str,
        memory_type: MemoryType | None = None,
    ) -> list[MemoryEntry]:
        """List active, non-expired memories owned strictly by session_id."""
        return await asyncio.to_thread(self._sync_list_session_memories, session_id, memory_type)

    def _sync_list_session_memories(
        self,
        session_id: str,
        memory_type: MemoryType | None = None,
    ) -> list[MemoryEntry]:
        conn = self._get_connection()
        now = time.time()
        try:
            if memory_type:
                query = """
                    SELECT * FROM memories
                    WHERE session_id = ? AND memory_type = ? AND (expires_at IS NULL OR expires_at > ?)
                    ORDER BY created_at DESC
                """
                rows = conn.execute(query, (session_id, memory_type.value, now)).fetchall()
            else:
                query = """
                    SELECT * FROM memories
                    WHERE session_id = ? AND (expires_at IS NULL OR expires_at > ?)
                    ORDER BY created_at DESC
                """
                rows = conn.execute(query, (session_id, now)).fetchall()

            return [self._row_to_entry(r) for r in rows]
        finally:
            conn.close()

    async def invalidate(self, memory_id: str, session_id: str) -> bool:
        """Mark a memory entry as invalidated enforcing session ownership."""
        return await asyncio.to_thread(self._sync_invalidate, memory_id, session_id)

    def _sync_invalidate(self, memory_id: str, session_id: str) -> bool:
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE memories
                    SET invalidated = 1, version = version + 1
                    WHERE memory_id = ? AND session_id = ?
                    """,
                    (memory_id, session_id),
                )
                return cursor.rowcount > 0
        finally:
            conn.close()

    async def prune_expired(self) -> int:
        """Prune expired memory entries based on TTL timestamps."""
        return await asyncio.to_thread(self._sync_prune_expired)

    def _sync_prune_expired(self) -> int:
        conn = self._get_connection()
        now = time.time()
        try:
            with conn:
                cursor = conn.execute("DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,))
                return cursor.rowcount
        finally:
            conn.close()

    async def clear_session(
        self,
        session_id: str,
        memory_type: MemoryType | None = None,
    ) -> int:
        """Clear memory entries for a specific session."""
        return await asyncio.to_thread(self._sync_clear_session, session_id, memory_type)

    def _sync_clear_session(
        self,
        session_id: str,
        memory_type: MemoryType | None = None,
    ) -> int:
        conn = self._get_connection()
        try:
            with conn:
                if memory_type:
                    cursor = conn.execute(
                        "DELETE FROM memories WHERE session_id = ? AND memory_type = ?",
                        (session_id, memory_type.value),
                    )
                else:
                    cursor = conn.execute("DELETE FROM memories WHERE session_id = ?", (session_id,))
                return cursor.rowcount
        finally:
            conn.close()

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        meta_dict = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        provenance = MemoryProvenance(
            source_type=row["source_type"],
            source_id=row["source_id"],
            confidence=row["confidence"],
            version=row["version"],
            invalidated=bool(row["invalidated"]),
        )
        return MemoryEntry(
            memory_id=row["memory_id"],
            session_id=row["session_id"],
            execution_id=row["execution_id"],
            memory_type=MemoryType(row["memory_type"]),
            content=row["content"],
            provenance=provenance,
            privacy_level=PrivacyLevel(row["privacy_level"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            metadata=meta_dict,
        )
