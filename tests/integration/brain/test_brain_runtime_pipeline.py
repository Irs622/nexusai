"""
Integration and acceptance tests for BrainRuntimeFacade and ExecutionPipeline (Milestone 3.1.7).
"""

from __future__ import annotations

import pytest

from nexusai.brain import (
    BrainRuntimeFacade,
    BrainSession,
    ExecutionPipeline,
    HistoryStage,
    PersistenceStage,
    PromptStage,
    ProviderStage,
    SessionState,
    TurnResponse,
)


@pytest.mark.asyncio
async def test_execution_pipeline_stages() -> None:
    """Verify ExecutionPipeline processes ExecutionContext through all stages sequentially."""
    pipeline = ExecutionPipeline(
        stages=[
            HistoryStage(),
            PromptStage(),
            ProviderStage(),
            PersistenceStage(),
        ]
    )

    facade = BrainRuntimeFacade(pipeline=pipeline)
    session = BrainSession()
    state = SessionState(provider_id="anthropic", active_model="claude-3.5-sonnet")
    ctx = facade.create_context(session, state)

    await pipeline.process(ctx)

    assert "assembled_context" in ctx.telemetry.metadata
    assert "prompt_bundle" in ctx.telemetry.metadata
    assert "execution_plan" in ctx.telemetry.metadata
    assert ctx.telemetry.metadata.get("persistence_scheduled") is True


@pytest.mark.asyncio
async def test_brain_runtime_facade_synchronous_turn() -> None:
    """Verify BrainRuntimeFacade.execute_turn performs synchronous turn orchestration."""
    facade = BrainRuntimeFacade()
    session = BrainSession()
    state = SessionState(provider_id="anthropic", active_model="claude-3.5-sonnet")

    response = await facade.execute_turn(
        session=session,
        state=state,
        user_prompt="Hello NexusAI",
    )

    assert isinstance(response, TurnResponse)
    assert response.turn.user_message.content == "Hello NexusAI"
    assert response.turn.status == "COMPLETED"
    assert "Hello NexusAI" in response.raw_response_text
    assert response.metrics.latency_ms >= 0.0
    assert state.turn_count == 1


@pytest.mark.asyncio
async def test_brain_runtime_facade_streaming_turn() -> None:
    """Verify BrainRuntimeFacade.stream_turn performs delta streaming turn orchestration."""
    facade = BrainRuntimeFacade()
    session = BrainSession()
    state = SessionState(provider_id="openrouter", active_model="claude-3.5-sonnet")

    stream = await facade.stream_turn(
        session=session,
        state=state,
        user_prompt="Stream me a response",
    )

    chunks = []
    async for chunk in stream:
        chunks.append(chunk)

    assert len(chunks) == 3
    assert stream.full_text == "NexusAI streaming response to 'Stream me a response'"
    assert state.turn_count == 1
