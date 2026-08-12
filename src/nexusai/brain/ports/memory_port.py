"""IMemoryStore, IMemoryRetriever, and IContextBuilder protocol contracts for Agent Context and Memory Lifecycle."""

from __future__ import annotations

from typing import Protocol

from nexusai.brain.domain.memory import MemoryEntry, MemoryQuery, MemoryType


class IMemoryStore(Protocol):
    """Abstract port for memory persistence, storage, and session-isolated CRUD operations."""

    async def store(self, entry: MemoryEntry) -> None:
        """Store a memory entry with session isolation and privacy sanitization."""
        ...

    async def load(self, memory_id: str, session_id: str) -> MemoryEntry | None:
        """Load a memory entry by ID enforcing strict session isolation."""
        ...

    async def list_session_memories(
        self,
        session_id: str,
        memory_type: MemoryType | None = None,
    ) -> list[MemoryEntry]:
        """List active memory entries owned strictly by session_id."""
        ...

    async def invalidate(self, memory_id: str, session_id: str) -> bool:
        """Mark a semantic or episodic memory entry as invalidated."""
        ...

    async def prune_expired(self) -> int:
        """Prune expired memory entries based on TTL timestamps."""
        ...

    async def clear_session(
        self,
        session_id: str,
        memory_type: MemoryType | None = None,
    ) -> int:
        """Clear memory entries for a specific session."""
        ...


class IMemoryRetriever(Protocol):
    """Abstract port for hybrid memory retrieval and relevance ranking."""

    async def retrieve(self, query: MemoryQuery) -> list[MemoryEntry]:
        """Retrieve memory entries matching session_id with recency and relevance scoring."""
        ...


class IContextBuilder(Protocol):
    """Abstract port for token budgeting, priority selection, and non-destructive context compaction."""

    async def build_context(
        self,
        session_id: str,
        query_text: str,
        max_tokens: int = 4096,
    ) -> tuple[str, list[MemoryEntry]]:
        """Construct non-destructive context representation strictly respecting token budget limits."""
        ...
