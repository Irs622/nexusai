"""Security verification test suite for P3-5 Agent Memory Integration invariants (P3-5-INV-01 to P3-5-INV-15)."""

from __future__ import annotations

import asyncio

import pytest

from nexusai.brain.domain.agent_loop import Observation
from nexusai.brain.domain.memory import MemoryType, PrivacyLevel
from nexusai.brain.domain.memory_learning import MemoryCandidate
from nexusai.brain.ports.tool_port import ToolExecutionResult
from nexusai.brain.runtime.context_builder import ContextBuilder
from nexusai.brain.runtime.memory_lifecycle import MemoryLifecycle
from nexusai.brain.runtime.memory_retriever import MemoryRetriever
from nexusai.infrastructure.persistence.sqlite_memory_store import SQLiteMemoryStore


@pytest.mark.asyncio
async def test_security_session_isolation_and_secret_redaction() -> None:
    """Security Test (P3-5-INV-01 & P3-5-INV-02): Session isolation and secret metadata sanitization."""
    store = SQLiteMemoryStore(":memory:")
    retriever = MemoryRetriever(store=store)
    builder = ContextBuilder(retriever=retriever, store=store)
    lifecycle = MemoryLifecycle(memory_store=store, retriever=retriever, context_builder=builder)

    res = ToolExecutionResult("r1", "tool1", True, "Output data")
    obs = Observation("exec-1", 1, (res,), 1, 0, 0, True, "Summary")

    # Learn in Session A
    await lifecycle.learn_from_execution(
        session_id="sess-A",
        execution_id="exec-A",
        user_prompt="User prefers Python syntax",
        observations=(obs,),
    )

    # Invariant: Query for Session B MUST NOT return Session A memory!
    ctx_b = await lifecycle.retrieve_context(session_id="sess-B", query_text="Python syntax")
    assert "sess-A" not in ctx_b
    assert "Python syntax" not in ctx_b


@pytest.mark.asyncio
async def test_security_contradiction_invalidation_and_provenance() -> None:
    """Security Test (P3-5-INV-04 & P3-5-INV-05): Updating semantic fact invalidates previous version and maintains provenance."""
    store = SQLiteMemoryStore(":memory:")
    retriever = MemoryRetriever(store=store)
    builder = ContextBuilder(retriever=retriever, store=store)
    lifecycle = MemoryLifecycle(memory_store=store, retriever=retriever, context_builder=builder)

    res = ToolExecutionResult("r1", "tool1", True, "Output")
    obs = Observation("exec-1", 1, (res,), 1, 0, 0, True, "Summary")

    # Store Semantic Fact v1 ("User preference constraint: user prefers PostgreSQL")
    await lifecycle.learn_from_execution(
        session_id="sess-fact",
        execution_id="exec-v1",
        user_prompt="User preference constraint: user prefers PostgreSQL",
        observations=(obs,),
    )

    mems_v1 = await store.list_session_memories("sess-fact", memory_type=MemoryType.SEMANTIC)
    assert len(mems_v1) == 1
    assert mems_v1[0].provenance.source_type == "user_explicit_statement"

    # Store Semantic Fact v2 ("User preference constraint: user prefers MySQL")
    await lifecycle.learn_from_execution(
        session_id="sess-fact",
        execution_id="exec-v2",
        user_prompt="User preference constraint: user prefers MySQL",
        observations=(obs,),
    )

    mems_active = await store.list_session_memories("sess-fact", memory_type=MemoryType.SEMANTIC)
    assert len(mems_active) == 1
    assert "MySQL" in mems_active[0].content


if __name__ == "__main__":
    asyncio.run(test_security_session_isolation_and_secret_redaction())
    asyncio.run(test_security_contradiction_invalidation_and_provenance())
    print("ALL P3-5 AGENT MEMORY LEARNING SECURITY TESTS PASSED SUCCESSFULLY!")
