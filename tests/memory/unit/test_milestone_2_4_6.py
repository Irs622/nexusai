"""
Unit tests for Milestone 2.4.6: Retrieval Engine Middleware Stages and ContextBuilder.
"""

import pytest

from nexusai.memory.domain import MemoryContent, MemoryMetadata, MemoryRecord, MemoryScope, MemoryType
from nexusai.memory.pipeline import ContextBuilder, PipelineBuilder, RetrievalPipelineConfig
from nexusai.memory.stages import (
    ImportanceStage,
    MetadataFilterStage,
    RankingStage,
    RecencyBoostStage,
    SimilarityStage,
)
from nexusai.memory.vector import InMemoryVectorStore


@pytest.mark.asyncio
async def test_retrieval_engine_middleware_stages():
    vector_store = InMemoryVectorStore(dimensions=4)

    # 1. Create candidate records
    rec1 = MemoryRecord(
        id="rec_1",
        memory_type=MemoryType.EPISODIC,
        scope=MemoryScope.SESSION,
        metadata=MemoryMetadata(importance=0.9, tags=["ai"]),
        content=MemoryContent(raw_text="NexusAI Core Memory Engine"),
    )
    rec2 = MemoryRecord(
        id="rec_2",
        memory_type=MemoryType.SEMANTIC,
        scope=MemoryScope.GLOBAL,
        metadata=MemoryMetadata(importance=0.2, tags=["legacy"]),
        content=MemoryContent(raw_text="Legacy content"),
    )

    # 2. Build composable retrieval pipeline
    pipeline = (
        PipelineBuilder(RetrievalPipelineConfig(max_candidates=5))
        .add_stage(MetadataFilterStage(required_tags=["ai"]))
        .add_stage(RecencyBoostStage())
        .add_stage(ImportanceStage())
        .add_stage(RankingStage())
        .build()
    )

    from nexusai.memory.contracts.retrieval import RetrievalContext
    context = RetrievalContext(
        query="Memory Engine",
        candidate_records=[rec1, rec2],
    )

    res = await pipeline.execute(context)

    # 3. Assertions
    assert len(res.records) == 1
    assert res.records[0].id == "rec_1"


def test_context_builder_formatting():
    builder = ContextBuilder(header="### Memory Context")
    rec = MemoryRecord(
        id="rec_ctx",
        content=MemoryContent(raw_text="Context builder test prompt payload"),
    )

    formatted = builder.build_context([rec])
    assert "### Memory Context" in formatted
    assert "Context builder test prompt payload" in formatted
