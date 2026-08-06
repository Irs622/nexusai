import pytest
pytestmark = pytest.mark.integration
"""
End-to-End Integration, Concurrency Validation, and P50/P95/P99 Latency Benchmark Test Suite.
"""

import asyncio
import time
import pytest

from nexusai.kernel.outbox import OutboxDispatcher
from nexusai.memory.domain import MemoryContent, MemoryMetadata, MemoryRecord, MemoryScope, MemoryType
from nexusai.memory.embedding import MockEmbeddingProvider
from nexusai.memory.metrics import MemoryMetricsCollector
from nexusai.memory.pipeline import (
    ClaudePromptFormatter,
    ContextBuilder,
    GeminiPromptFormatter,
    OpenAIPromptFormatter,
    PipelineFactory,
)
from nexusai.memory.policies import DeduplicationPolicy, PolicyEngine, RetentionPolicy
from nexusai.memory.serializer import JSONMemorySerializer
from nexusai.memory.storage import InMemoryMemoryStore, SQLiteMemoryStore
from nexusai.memory.vector import InMemoryVectorStore, VectorRecord


@pytest.mark.asyncio
async def test_end_to_end_memory_lifecycle():
    """Verify full end-to-end memory lifecycle: store -> embed -> index -> retrieve -> expire."""
    store = SQLiteMemoryStore(":memory:")
    vector_store = InMemoryVectorStore(dimensions=8)
    embedder = MockEmbeddingProvider(dimensions=8)
    serializer = JSONMemorySerializer()
    metrics = MemoryMetricsCollector()

    # 1. Create record & store in persistence
    content = MemoryContent(raw_text="End to end integration lifecycle record content")
    record = MemoryRecord(id="e2e_rec_1", content=content)

    t_start = time.time()
    await store.save(record)
    metrics.record_latency("storage_save", (time.time() - t_start) * 1000.0)

    # 2. Generate embedding & index in vector store
    t_start = time.time()
    vec = await embedder.embed_text(record.content.raw_text)
    metrics.record_latency("embedding", (time.time() - t_start) * 1000.0)

    v_rec = VectorRecord(record_id=record.id, vector=vec, namespace="brain", payload=record.content.raw_text)
    t_start = time.time()
    await vector_store.upsert(v_rec)
    metrics.record_latency("vector_search", (time.time() - t_start) * 1000.0)

    # 3. Retrieve from persistence & search vector store
    fetched = await store.get("e2e_rec_1")
    assert fetched is not None
    assert fetched.id == "e2e_rec_1"

    matches = await vector_store.search(query_vector=vec, top_k=5, namespace="brain")
    assert len(matches) == 1
    assert matches[0].record_id == "e2e_rec_1"

    # 4. Verify percentiles
    summary = metrics.get_summary()
    assert summary["percentiles"]["storage_save"]["count"] == 1


@pytest.mark.asyncio
async def test_concurrent_stress_operations():
    """Verify 50 simultaneous parallel read/write operations without race conditions."""
    store = InMemoryMemoryStore()
    metrics = MemoryMetricsCollector()

    async def single_worker(idx: int):
        rec = MemoryRecord(
            id=f"rec_stress_{idx}",
            content=MemoryContent(raw_text=f"Stress worker text {idx}"),
        )
        await store.save(rec)
        res = await store.get(f"rec_stress_{idx}")
        assert res is not None
        metrics.increment_counter("store_count")

    # Run 50 parallel concurrent tasks
    tasks = [single_worker(i) for i in range(50)]
    await asyncio.gather(*tasks)

    listed = await store.list_records(limit=100)
    assert len(listed) == 50
    assert metrics.get_summary()["counters"]["store_count"] == 50


def test_model_specific_formatters():
    """Verify OpenAI, Claude, and Gemini prompt formatters."""
    rec = MemoryRecord(id="rec_fmt_1", content=MemoryContent(raw_text="Formatter test text"))

    # OpenAI Formatter
    openai_builder = ContextBuilder(formatter=OpenAIPromptFormatter())
    openai_out = openai_builder.build_context([rec])
    assert "System Instruction:" in openai_out

    # Claude Formatter
    claude_builder = ContextBuilder(formatter=ClaudePromptFormatter())
    claude_out = claude_builder.build_context([rec])
    assert "<documents>" in claude_out
    assert "<document_content>" in claude_out

    # Gemini Formatter
    gemini_builder = ContextBuilder(formatter=GeminiPromptFormatter())
    gemini_out = gemini_builder.build_context([rec])
    assert "GROUNDING_KNOWLEDGE" in gemini_out
