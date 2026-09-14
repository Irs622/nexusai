"""
Async SQLite Implementation for Short-Term Session Memory.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

import aiosqlite

from nexusai.core.errors import SecurityError
from nexusai.memory.base import BaseMemory


class SQLiteMemory(BaseMemory):
    """Asynchronous SQLite memory store using aiosqlite with multi-tenant session isolation."""

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

        # 1. Sessions table for tenant/user ownership verification
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_tenant_user ON sessions(tenant_id, user_id);"
        )

        # 2. Messages table with tenant_id and user_id columns
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                user_id TEXT NOT NULL DEFAULT 'anonymous',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                name TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Migration: Add tenant_id / user_id columns if table existed without them
        async with self._db.execute("PRAGMA table_info(messages);") as cursor:
            cols = [row[1] for row in await cursor.fetchall()]
            if "tenant_id" not in cols:
                await self._db.execute(
                    "ALTER TABLE messages ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default';"
                )
            if "user_id" not in cols:
                await self._db.execute(
                    "ALTER TABLE messages ADD COLUMN user_id TEXT NOT NULL DEFAULT 'anonymous';"
                )

        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_tenant_session ON messages(tenant_id, session_id, id);"
        )
        await self._db.commit()
        self._initialized = True

    async def _get_db(self) -> aiosqlite.Connection:
        """Ensure database is initialized and return persistent connection."""
        if self._db is None or not self._initialized:
            await self.initialize_db()
        assert self._db is not None
        return self._db

    async def get_or_create_session(
        self,
        session_id: str | None,
        tenant_id: str = "default",
        user_id: str = "anonymous",
    ) -> str:
        """Verify session ownership or issue a cryptographically random session ID."""
        db = await self._get_db()
        if not session_id:
            # Issue unguessable server-side random session ID
            new_session_id = f"session_{secrets.token_urlsafe(32)}"
            await db.execute(
                "INSERT INTO sessions (session_id, tenant_id, user_id) VALUES (?, ?, ?);",
                (new_session_id, tenant_id, user_id),
            )
            await db.commit()
            return new_session_id

        # Verify existing session ownership
        async with db.execute(
            "SELECT tenant_id, user_id FROM sessions WHERE session_id = ?;",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if row is not None:
            existing_tenant, existing_user = row[0], row[1]
            if existing_tenant != tenant_id or existing_user != user_id:
                raise SecurityError(
                    f"Session ownership verification failed: session '{session_id}' belongs to another tenant/user",
                    details={
                        "session_id": session_id,
                        "expected_tenant": tenant_id,
                        "session_tenant": existing_tenant,
                    },
                )
            return session_id

        # Session ID supplied by client but not yet in database -> register ownership
        await db.execute(
            "INSERT INTO sessions (session_id, tenant_id, user_id) VALUES (?, ?, ?);",
            (session_id, tenant_id, user_id),
        )
        await db.commit()
        return session_id

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        name: str | None = None,
        tenant_id: str = "default",
        user_id: str = "anonymous",
    ) -> None:
        """Insert a new message into SQLite table scoped by tenant and user."""
        db = await self._get_db()
        await db.execute(
            "INSERT INTO messages (session_id, tenant_id, user_id, role, content, name) VALUES (?, ?, ?, ?, ?, ?);",
            (session_id, tenant_id, user_id, role, content, name),
        )
        await db.commit()

    async def get_messages(
        self,
        session_id: str,
        limit: int = 50,
        tenant_id: str = "default",
    ) -> list[dict[str, Any]]:
        """Retrieve latest messages for session ordered chronologically, filtered by tenant."""
        db = await self._get_db()
        async with db.execute(
            """
            SELECT role, content, name FROM (
                SELECT id, role, content, name FROM messages
                WHERE session_id = ? AND tenant_id = ?
                ORDER BY id DESC LIMIT ?
            ) ORDER BY id ASC;
            """,
            (session_id, tenant_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()

        result: list[dict[str, Any]] = []
        for role, content, name in rows:
            msg: dict[str, Any] = {"role": role, "content": content}
            if name:
                msg["name"] = name
            result.append(msg)

        return result

    async def clear_session(
        self,
        session_id: str,
        tenant_id: str = "default",
    ) -> None:
        """Delete all stored messages and session record for a specific session scoped by tenant."""
        db = await self._get_db()
        await db.execute(
            "DELETE FROM messages WHERE session_id = ? AND tenant_id = ?;",
            (session_id, tenant_id),
        )
        await db.execute(
            "DELETE FROM sessions WHERE session_id = ? AND tenant_id = ?;",
            (session_id, tenant_id),
        )
        await db.commit()

    async def close(self) -> None:
        """Close persistent SQLite database connection cleanly."""
        if self._db is not None:
            await self._db.close()
            self._db = None
            self._initialized = False
