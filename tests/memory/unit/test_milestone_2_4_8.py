"""
Unit tests for Milestone 2.4.8: OutboxDispatcher, Domain vs Integration Events, PipelineTrace exports, PromptFormatters, and DeduplicationPolicy.
"""

import pytest

from nexusai.kernel.outbox import (
    EmbeddingCompletedEvent,
    MemoryStoredEvent,
    OutboxDispatcher,
    OutboxRecord,
)
from nexusai.memory.domain import MemoryContent, MemoryMetadata, MemoryRecord
from nexusai.memory.pipeline import (
    ContextBuilder,
    JSONPromptFormatter,
    MarkdownPromptFormatter,
    XMLPromptFormatter,
)
from nexusai.memory.policies import DeduplicationPolicy, PolicyEngine
from nexusai.memory.stages import WeightedScoringStage


def test_domain_vs_integration_events():
    domain_event = MemoryStoredEvent(record_id="rec_1", scope="user", memory_type="semantic")
    assert domain_event.header.event_type == "MemoryStoredEvent"
    assert domain_event.payload["record_id"] == "rec_1"

    integ_event = EmbeddingCompletedEvent(record_id="rec_1", dimensions=768)
    assert integ_event.header.event_type == "EmbeddingCompletedEvent"
    assert integ_event.payload["dimensions"] == 768


def test_pipeline_trace_exports():
    from nexusai.memory.contracts.retrieval import PipelineTrace, StageTrace

    trace = PipelineTrace(
        total_latency_ms=12.5,
        initial_count=10,
        final_count=3,
        stage_traces=[
            StageTrace(stage_name="SimilarityStage", input_count=10, output_count=5, latency_ms=4.2, dropped_count=5),
            StageTrace(stage_name="RankingStage", input_count=5, output_count=3, latency_ms=1.1, dropped_count=2),
        ],
    )

    d = trace.to_dict()
    assert d["total_latency_ms"] == 12.5

    j = trace.to_json()
    assert "SimilarityStage" in j

    otel = trace.to_otel()
    assert len(otel) == 2
    assert otel[0]["name"] == "stage.similaritystage"

    printed = trace.pretty_print()
    assert "[TRACE] Pipeline Total Latency" in printed


def test_prompt_formatters():
    rec = MemoryRecord(id="rec_fmt", content=MemoryContent(raw_text="Formatter test text"))

    md_builder = ContextBuilder(formatter=MarkdownPromptFormatter())
    md_out = md_builder.build_context([rec])
    assert "### Retrieved Memory Context" in md_out

    json_builder = ContextBuilder(formatter=JSONPromptFormatter())
    json_out = json_builder.build_context([rec])
    assert '"content": "Formatter test text"' in json_out

    xml_builder = ContextBuilder(formatter=XMLPromptFormatter())
    xml_out = xml_builder.build_context([rec])
    assert "<retrieved_context>" in xml_out


@pytest.mark.asyncio
async def test_deduplication_policy():
    rec1 = MemoryRecord(id="rec_1", content=MemoryContent(raw_text="Exact duplicate text"))
    rec2 = MemoryRecord(id="rec_2", content=MemoryContent(raw_text="Exact duplicate text"))
    rec3 = MemoryRecord(id="rec_3", content=MemoryContent(raw_text="Unique text"))

    engine = PolicyEngine(policies=[DeduplicationPolicy()])
    ctx = await engine.evaluate_policies([rec1, rec2, rec3])

    assert len(ctx.retained_records) == 2
    assert len(ctx.expired_records) == 1
    assert ctx.expired_records[0].id == "rec_2"
