"""
Async SQLite Implementation for Short-Term Session Memory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite

from nexusai.memory.base import BaseMemory


class SQLiteMemory(BaseMemory):
    """Asynchronous SQLite memory store using aiosqlite."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._db: aiosqlite.Connection | None = None
        self._initialized = False

    async def initialize_db(self) -> None:
        """Initialize SQLite table schemas and persistent db connection."""
        if self._db is None:
            if self.db_path != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(self.db_path)

        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                name TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);"
        )
        await self._db.commit()
        self._initialized = True

    async def _get_db(self) -> aiosqlite.Connection:
        """Ensure database is initialized and return persistent connection."""
        if self._db is None or not self._initialized:
            await self.initialize_db()
        assert self._db is not None
        return self._db

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        name: str | None = None,
    ) -> None:
        """Insert a new message into SQLite table."""
        db = await self._get_db()
        await db.execute(
            "INSERT INTO messages (session_id, role, content, name) VALUES (?, ?, ?, ?);",
            (session_id, role, content, name),
        )
        await db.commit()

    async def get_messages(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve latest messages for session ordered chronologically."""
        db = await self._get_db()
        async with db.execute(
            """
            SELECT role, content, name FROM (
                SELECT id, role, content, name FROM messages
                WHERE session_id = ?
                ORDER BY id DESC LIMIT ?
            ) ORDER BY id ASC;
            """,
            (session_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()

        result: list[dict[str, Any]] = []
        for role, content, name in rows:
            msg: dict[str, Any] = {"role": role, "content": content}
            if name:
                msg["name"] = name
            result.append(msg)

        return result

    async def clear_session(self, session_id: str) -> None:
        """Delete all stored messages for a specific session."""
        db = await self._get_db()
        await db.execute(
            "DELETE FROM messages WHERE session_id = ?;",
            (session_id,),
        )
        await db.commit()

    async def close(self) -> None:
        """Close persistent SQLite database connection cleanly."""
        if self._db is not None:
            await self._db.close()
            self._db = None
            self._initialized = False
