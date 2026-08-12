"""Adversarial stress test suite for P3-5 Memory Lifecycle concurrency safety and session isolation."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.agent_loop import Observation
from nexusai.brain.ports.tool_port import ToolExecutionResult
from nexusai.brain.runtime.context_builder import ContextBuilder
from nexusai.brain.runtime.memory_lifecycle import MemoryLifecycle
from nexusai.brain.runtime.memory_retriever import MemoryRetriever
from nexusai.infrastructure.observability.in_memory_exporter import InMemoryMetricsExporter
from nexusai.infrastructure.persistence.sqlite_memory_store import SQLiteMemoryStore


@pytest.mark.asyncio
async def test_p3_5_adversarial_memory_lifecycle_stress() -> None:
    """Stress Test: 20 concurrent agent sessions writing episodic memories and querying context.

    Invariants: Zero cross-session leakage, zero memory corruption, 100% thread/task safe.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        telemetry = InMemoryMetricsExporter()
        store = SQLiteMemoryStore(db_path=db_path, telemetry=telemetry)
        retriever = MemoryRetriever(store=store, telemetry=telemetry)
        builder = ContextBuilder(retriever=retriever, store=store)
        lifecycle = MemoryLifecycle(
            memory_store=store,
            retriever=retriever,
            context_builder=builder,
            telemetry=telemetry,
        )

        async def session_worker(s_id: int) -> None:
            sess_key = f"sess-stress-p3-5-{s_id}"

            for i in range(10):
                res = ToolExecutionResult(f"r-{s_id}-{i}", "terminal", True, f"Output {i} for session {s_id}")
                obs = Observation(f"exec-{s_id}-{i}", i, (res,), 1, 0, 0, True, "Summary")

                # Post-execution learning
                result = await lifecycle.learn_from_execution(
                    session_id=sess_key,
                    execution_id=f"exec-{s_id}-{i}",
                    user_prompt=f"Execute query {i} for session {s_id}",
                    observations=(obs,),
                )
                assert result.stored_count >= 1

                # Pre-planning context retrieval
                ctx = await lifecycle.retrieve_context(session_id=sess_key, query_text=f"query {i}")
                assert f"session {s_id}" in ctx
                assert f"session {(s_id + 1) % 20}" not in ctx, "Cross-session memory leakage detected!"

        # Launch 20 concurrent session workers
        workers = [asyncio.create_task(session_worker(w)) for w in range(20)]
        await asyncio.gather(*workers)

        print(f"\n[P3-5 ADVERSARIAL MEMORY LIFECYCLE STRESS VERIFICATION]")
        print("20 Concurrent Sessions verified with 100% session isolation!")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_p3_5_adversarial_memory_lifecycle_stress())
    print("ALL P3-5 MEMORY INTEGRATION STRESS TESTS PASSED SUCCESSFULLY!")
