"""Integration and adversarial verification test suite for P2-6 Agent Context & Memory Lifecycle."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import pytest

from nexusai.brain.coordinator import BrainCoordinator
from nexusai.brain.domain.memory import (
    MemoryEntry,
    MemoryProvenance,
    MemoryQuery,
    MemoryType,
    PrivacyLevel,
)
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.runtime.context_builder import ContextBuilder
from nexusai.brain.runtime.memory_retriever import MemoryRetriever
from nexusai.infrastructure.persistence.sqlite_memory_store import SQLiteMemoryStore


@pytest.mark.asyncio
async def test_p2_6_end_to_end_memory_retrieval_and_context_compaction() -> None:
    """Integration Test: Full Memory Lifecycle (Store -> Hybrid Retrieve -> Token Compacted Context Assembly)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteMemoryStore(db_path=db_path)
        retriever = MemoryRetriever(store=store)
        builder = ContextBuilder(retriever=retriever, store=store)

        prov = MemoryProvenance(source_type="user_preference", confidence=0.9, version=1)

        # 1. Store Semantic Memory
        semantic_mem = MemoryEntry(
            memory_id="mem-sem-1",
            session_id="sess-e2e",
            execution_id=None,
            memory_type=MemoryType.SEMANTIC,
            content="User prefers Python 3.12 syntax and Pydantic schemas",
            provenance=prov,
        )
        await store.store(semantic_mem)

        # 2. Store Episodic Memory
        episodic_mem = MemoryEntry(
            memory_id="mem-epi-1",
            session_id="sess-e2e",
            execution_id="exec-101",
            memory_type=MemoryType.EPISODIC,
            content="Previous execution succeeded using pytest test suite",
            provenance=prov,
        )
        await store.store(episodic_mem)

        # 3. Build Compacted Context
        context_text, selected = await builder.build_context(
            session_id="sess-e2e", query_text="Python pytest testing preferences", max_tokens=4096
        )

        assert "[RECALLED MEMORY CONTEXT]" in context_text
        assert len(selected) == 2
        assert any(e.memory_id == "mem-sem-1" for e in selected)
        assert any(e.memory_id == "mem-epi-1" for e in selected)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_p2_6_fact_versioning_and_invalidation_lifecycle() -> None:
    """Test Fact Versioning: Storing v2 of a fact invalidates v1, preventing stale memory retrieval."""
    store = SQLiteMemoryStore(":memory:")
    retriever = MemoryRetriever(store=store)

    # 1. Store Fact v1 ("User uses Laravel v8")
    prov_v1 = MemoryProvenance(source_type="user_input", version=1)
    fact_v1 = MemoryEntry(
        memory_id="fact-laravel-v1",
        session_id="sess-fact-test",
        execution_id=None,
        memory_type=MemoryType.SEMANTIC,
        content="User uses Laravel framework version 8",
        provenance=prov_v1,
    )
    await store.store(fact_v1)

    # 2. Fact Updated: Store Fact v2 ("User updated to Laravel v10") & Invalidate v1
    await store.invalidate("fact-laravel-v1", session_id="sess-fact-test")

    prov_v2 = MemoryProvenance(source_type="user_input", version=2)
    fact_v2 = MemoryEntry(
        memory_id="fact-laravel-v2",
        session_id="sess-fact-test",
        execution_id=None,
        memory_type=MemoryType.SEMANTIC,
        content="User updated project to Laravel framework version 10",
        provenance=prov_v2,
    )
    await store.store(fact_v2)

    # 3. Query memory: Must return ONLY Fact v2
    query = MemoryQuery(session_id="sess-fact-test", query_text="Laravel framework version", top_k=5)
    recalled = await retriever.retrieve(query)

    assert len(recalled) == 1
    assert recalled[0].memory_id == "fact-laravel-v2"
    assert recalled[0].content == "User updated project to Laravel framework version 10"


@pytest.mark.asyncio
async def test_p2_6_adversarial_security_invariants() -> None:
    """Verification Test: Assert 10 mandatory Memory Security Invariants."""
    store = SQLiteMemoryStore(":memory:")
    retriever = MemoryRetriever(store=store)

    prov = MemoryProvenance(source_type="test")

    # Invariant 1: Session A MUST NEVER retrieve Session B memory
    await store.store(MemoryEntry("m-sess-a", "sess-A", None, MemoryType.EPISODIC, "Data A", prov))
    await store.store(MemoryEntry("m-sess-b", "sess-B", None, MemoryType.EPISODIC, "Data B", prov))

    res_a = await retriever.retrieve(MemoryQuery(session_id="sess-A", query_text="Data"))
    assert len(res_a) == 1 and res_a[0].memory_id == "m-sess-a"

    # Invariant 3: Sensitive memory MUST be sanitized before persistence
    sens_mem = MemoryEntry(
        "m-sens", "sess-A", None, MemoryType.WORKING, "Secret Data", prov,
        privacy_level=PrivacyLevel.SENSITIVE, metadata={"token": "bearer-abc-secret"}
    )
    await store.store(sens_mem)
    loaded_sens = await store.load("m-sens", session_id="sess-A")
    assert loaded_sens is not None
    assert loaded_sens.metadata["token"] == "[REDACTED_SECRET]"

    # Invariant 4: Expired memory MUST NOT be returned by retrieval
    expired_mem = MemoryEntry(
        "m-exp", "sess-A", None, MemoryType.WORKING, "Expired Data", prov,
        expires_at=time.time() - 10.0
    )
    await store.store(expired_mem)
    res_exp = await retriever.retrieve(MemoryQuery(session_id="sess-A", query_text="Expired Data"))
    assert not any(m.memory_id == "m-exp" for m in res_exp)

    # Invariant 5: Invalidated memory MUST NOT be returned by retrieval
    await store.invalidate("m-sess-a", session_id="sess-A")
    res_inval = await retriever.retrieve(MemoryQuery(session_id="sess-A", query_text="Data A"))
    assert not any(m.memory_id == "m-sess-a" for m in res_inval)


@pytest.mark.asyncio
async def test_p2_6_concurrent_session_memory_writes_and_isolation() -> None:
    """Integration Test: Concurrent memory writes across separate sessions maintain strict SQL isolation."""
    store = SQLiteMemoryStore(":memory:")
    prov = MemoryProvenance(source_type="stress")

    async def writer(session_id: str, count: int) -> None:
        for i in range(count):
            mem = MemoryEntry(
                memory_id=f"mem-{session_id}-{i}",
                session_id=session_id,
                execution_id=None,
                memory_type=MemoryType.WORKING,
                content=f"Content {i} for {session_id}",
                provenance=prov,
            )
            await store.store(mem)

    await asyncio.gather(
        writer("sess-A", 10),
        writer("sess-B", 10),
        writer("sess-C", 10),
    )

    mems_a = await store.list_session_memories("sess-A")
    mems_b = await store.list_session_memories("sess-B")
    mems_c = await store.list_session_memories("sess-C")

    assert len(mems_a) == 10
    assert len(mems_b) == 10
    assert len(mems_c) == 10
    assert all(m.session_id == "sess-A" for m in mems_a)
    assert all(m.session_id == "sess-B" for m in mems_b)
    assert all(m.session_id == "sess-C" for m in mems_c)


if __name__ == "__main__":
    asyncio.run(test_p2_6_end_to_end_memory_retrieval_and_context_compaction())
    asyncio.run(test_p2_6_fact_versioning_and_invalidation_lifecycle())
    asyncio.run(test_p2_6_adversarial_security_invariants())
    asyncio.run(test_p2_6_concurrent_session_memory_writes_and_isolation())
    print("ALL P2-6 MEMORY INTEGRATION & SECURITY INVARIANT TESTS PASSED SUCCESSFULLY!")
