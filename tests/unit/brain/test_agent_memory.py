"""Unit tests for P2-6 Agent Memory Domain, Provenance, Privacy Boundaries, and SQLite Store."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import pytest

from nexusai.brain.domain.memory import (
    MemoryEntry,
    MemoryProvenance,
    MemoryQuery,
    MemoryType,
    PrivacyLevel,
)
from nexusai.brain.runtime.context_builder import ContextBuilder, estimate_token_count
from nexusai.brain.runtime.memory_retriever import MemoryRetriever
from nexusai.infrastructure.persistence.sqlite_memory_store import SQLiteMemoryStore


@pytest.mark.asyncio
async def test_memory_entry_provenance_and_privacy_redaction() -> None:
    """Test MemoryEntry creation, provenance tracking, and metadata secret redaction."""
    provenance = MemoryProvenance(source_type="user_input", confidence=0.95, version=1)
    entry = MemoryEntry(
        memory_id="mem-1",
        session_id="sess-1",
        execution_id="exec-1",
        memory_type=MemoryType.SEMANTIC,
        content="User prefers Python 3.12 syntax",
        provenance=provenance,
        privacy_level=PrivacyLevel.SENSITIVE,
        metadata={"user": "alice", "api_key": "secret-token-123"},
    )

    assert entry.memory_id == "mem-1"
    assert entry.provenance.source_type == "user_input"
    assert entry.metadata["user"] == "alice"
    assert entry.metadata["api_key"] == "[REDACTED_SECRET]", "Secret keys must be redacted at post-init"


@pytest.mark.asyncio
async def test_strict_sql_session_isolation() -> None:
    """Test Session Isolation: Session A queries strictly cannot return memories belonging to Session B."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteMemoryStore(db_path=db_path)
        prov = MemoryProvenance(source_type="test")

        mem_a = MemoryEntry(
            memory_id="mem-a", session_id="sess-A", execution_id=None,
            memory_type=MemoryType.EPISODIC, content="Secret for Session A", provenance=prov,
        )
        mem_b = MemoryEntry(
            memory_id="mem-b", session_id="sess-B", execution_id=None,
            memory_type=MemoryType.EPISODIC, content="Secret for Session B", provenance=prov,
        )

        await store.store(mem_a)
        await store.store(mem_b)

        # SQL load for Session A must NOT return mem_b
        assert await store.load("mem-a", session_id="sess-A") is not None
        assert await store.load("mem-b", session_id="sess-A") is None, "Cross-session load must return None"

        mems_a = await store.list_session_memories("sess-A")
        assert len(mems_a) == 1
        assert mems_a[0].memory_id == "mem-a"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_memory_invalidation_and_ttl_pruning() -> None:
    """Test Invalidation & TTL Pruning: Invalidated and expired entries are filtered correctly."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteMemoryStore(db_path=db_path)
        prov = MemoryProvenance(source_type="test")
        now = time.time()

        valid_mem = MemoryEntry(
            memory_id="m-valid", session_id="sess-1", execution_id=None,
            memory_type=MemoryType.EPISODIC, content="Valid Memory", provenance=prov,
        )
        expired_mem = MemoryEntry(
            memory_id="m-expired", session_id="sess-1", execution_id=None,
            memory_type=MemoryType.WORKING, content="Expired Memory", provenance=prov,
            expires_at=now - 5.0,  # Expired 5s ago
        )

        await store.store(valid_mem)
        await store.store(expired_mem)

        # list_session_memories filters expired automatically
        active = await store.list_session_memories("sess-1")
        assert len(active) == 1
        assert active[0].memory_id == "m-valid"

        # Explicit prune returns count of deleted entries
        pruned_cnt = await store.prune_expired()
        assert pruned_cnt == 1

        # Test Invalidation
        assert await store.invalidate("m-valid", session_id="sess-1") is True
        loaded = await store.load("m-valid", session_id="sess-1")
        assert loaded is not None
        assert loaded.provenance.invalidated is True
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_non_destructive_context_compaction_and_token_budgeting() -> None:
    """Test Non-Destructive Compaction: ContextBuilder respects max_tokens without mutating stored entries."""
    store = SQLiteMemoryStore(":memory:")
    retriever = MemoryRetriever(store=store)
    builder = ContextBuilder(retriever=retriever, store=store, reserved_system_tokens=100)

    prov = MemoryProvenance(source_type="user")
    for i in range(10):
        entry = MemoryEntry(
            memory_id=f"m-{i}",
            session_id="sess-budget",
            execution_id=None,
            memory_type=MemoryType.EPISODIC,
            content=f"Important memory item number {i} containing detailed execution notes",
            provenance=prov,
        )
        await store.store(entry)

    # Build context with budget limit of 150 tokens
    context_str, selected = await builder.build_context("sess-budget", "execution notes", max_tokens=150)

    assert "[RECALLED MEMORY CONTEXT]" in context_str
    assert len(selected) < 10, "Compaction must select only memories fitting within token budget"

    # Confirm original memory entries in store were NOT mutated or summarized
    stored_entry = await store.load("m-0", session_id="sess-budget")
    assert stored_entry is not None
    assert stored_entry.content == "Important memory item number 0 containing detailed execution notes"


if __name__ == "__main__":
    asyncio.run(test_memory_entry_provenance_and_privacy_redaction())
    asyncio.run(test_strict_sql_session_isolation())
    asyncio.run(test_memory_invalidation_and_ttl_pruning())
    asyncio.run(test_non_destructive_context_compaction_and_token_budgeting())
    print("ALL P2-6 AGENT MEMORY UNIT TESTS PASSED SUCCESSFULLY!")
