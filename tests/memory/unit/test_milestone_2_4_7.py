"""
Unit tests for Milestone 2.4.7: PipelineTrace telemetry, WeightedScoringStage, ContextBuilder strategies, and PolicyEngine.
"""

import pytest

from nexusai.memory.domain import MemoryContent, MemoryMetadata, MemoryRecord, MemoryScope, MemoryType
from nexusai.memory.pipeline import ContextBuilder, PipelineBuilder, RetrievalPipelineConfig
from nexusai.memory.policies import PolicyEngine, RetentionPolicy
from nexusai.memory.stages import (
    ImportanceStage,
    MetadataFilterStage,
    RankingStage,
    RecencyBoostStage,
    SimilarityStage,
    WeightedScoringStage,
)
from nexusai.memory.vector import InMemoryVectorStore


@pytest.mark.asyncio
async def test_pipeline_trace_telemetry():
    vector_store = InMemoryVectorStore(dimensions=4)

    rec1 = MemoryRecord(
        id="rec_1",
        memory_type=MemoryType.EPISODIC,
        scope=MemoryScope.SESSION,
        metadata=MemoryMetadata(importance=0.8, tags=["telemetry"]),
        content=MemoryContent(raw_text="Telemetry test candidate 1"),
    )

    pipeline = (
        PipelineBuilder(
            RetrievalPipelineConfig(
                max_candidates=5,
                weights={"similarity": 0.5, "recency": 0.3, "importance": 0.2},
            )
        )
        .add_stage(SimilarityStage(vector_store))
        .add_stage(RecencyBoostStage())
        .add_stage(ImportanceStage())
        .add_stage(WeightedScoringStage())
        .add_stage(RankingStage())
        .build()
    )

    from nexusai.memory.contracts.retrieval import RetrievalContext
    context = RetrievalContext(query="Telemetry", candidate_records=[rec1])

    result = await pipeline.execute(context)

    assert result.trace is not None
    assert len(result.trace.stage_traces) == 5
    assert result.trace.stage_traces[0].stage_name == "SimilarityStage"
    assert result.trace.stage_traces[0].latency_ms >= 0.0


def test_context_builder_strategies():
    rec1 = MemoryRecord(
        id="rec_conv",
        metadata=MemoryMetadata(source="agent", tags=["ai"]),
        content=MemoryContent(raw_text="User wants plugin installation."),
    )

    builder_conv = ContextBuilder(strategy="conversation")
    conv_text = builder_conv.build_context([rec1])
    assert "User wants plugin installation." in conv_text
    assert "SESSION" in conv_text

    builder_know = ContextBuilder(strategy="knowledge")
    know_text = builder_know.build_context([rec1])
    assert "User wants plugin installation." in know_text


@pytest.mark.asyncio
async def test_policy_engine_retention():
    rec_valid = MemoryRecord(
        id="rec_valid",
        metadata=MemoryMetadata(ttl_seconds=3600),
        content=MemoryContent(raw_text="Valid record"),
    )
    rec_expired = MemoryRecord(
        id="rec_expired",
        metadata=MemoryMetadata(ttl_seconds=1.0, created_at=1000.0),
        content=MemoryContent(raw_text="Expired record"),
    )

    engine = PolicyEngine(policies=[RetentionPolicy(default_max_age_days=1.0)])
    ctx = await engine.evaluate_policies([rec_valid, rec_expired])

    assert len(ctx.retained_records) == 1
    assert ctx.retained_records[0].id == "rec_valid"
    assert len(ctx.expired_records) == 1
    assert ctx.expired_records[0].id == "rec_expired"
