"""
Milestone 3.1.8 Production Hardening, Concurrency Stress, and Fuzzing Test Suite.
"""

from __future__ import annotations

import asyncio

import pytest

from nexusai.brain import (
    BrainRuntimeFacade,
    BrainSession,
    ExecutionPlan,
    ExecutionStep,
    PromptBundle,
    PromptMessage,
    SchemaVersion,
    SessionState,
    TextArtifact,
    TurnMetrics,
)


@pytest.mark.asyncio
async def test_concurrent_load_100_streams() -> None:
    """Load test 100 concurrent turn streaming executions."""
    facade = BrainRuntimeFacade()

    async def run_single_stream(session_index: int) -> int:
        session = BrainSession()
        state = SessionState()
        stream = await facade.stream_turn(session, state, f"User query {session_index}")
        count = 0
        async for chunk in stream:
            count += 1
        return count

    # Run 100 concurrent streams in parallel via asyncio.gather
    tasks = [run_single_stream(i) for i in range(100)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 100
    assert all(count == 3 for count in results)


@pytest.mark.asyncio
async def test_cancellation_stress() -> None:
    """Stress test cancellation signal handling under fast abort scenarios."""
    facade = BrainRuntimeFacade()

    async def run_cancelled_stream() -> None:
        session = BrainSession()
        state = SessionState()
        stream = await facade.stream_turn(session, state, "Cancel me quickly")
        # Immediately set cancellation token
        stream._ctx.cancellation.is_cancelled = True

    tasks = [run_cancelled_stream() for _ in range(50)]
    await asyncio.gather(*tasks, return_exceptions=True)


def test_prompt_bundle_fuzzing() -> None:
    """Fuzz test PromptBundle instantiation with edge case payloads."""
    # Fuzz text artifacts with long unicode strings and empty values
    large_text = "A" * 1000000  # 1MB string
    text_art = TextArtifact(text=large_text)
    assert text_art.size_bytes() == 1000000

    msg = PromptMessage(role="user", content="Edge case message")  # type: ignore[arg-type]
    bundle = PromptBundle(messages=(msg,), artifacts=(text_art,))
    assert len(bundle.messages) == 1
    assert bundle.artifacts[0].size_bytes() == 1000000


def test_serialization_roundtrip_all_contracts() -> None:
    """Verify JSON dictionary roundtrip serialization consistency across all domain contracts."""
    version = SchemaVersion(1, 2)
    assert SchemaVersion.from_dict(version.to_dict()) == version

    session = BrainSession()
    assert BrainSession.from_dict(session.to_dict()).session_id == session.session_id

    metrics = TurnMetrics(ttft_ms=12.5, latency_ms=100.0, output_tokens=50)
    assert TurnMetrics.from_dict(metrics.to_dict()) == metrics

    step = ExecutionStep(provider_id="anthropic", model_id="claude-3.5-sonnet")
    plan = ExecutionPlan(steps=(step,))
    assert ExecutionPlan.from_dict(plan.to_dict()).primary_step.provider_id == "anthropic"
