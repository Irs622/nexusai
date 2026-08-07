"""
Unit tests for Milestone 3.1.5 Delta Streaming Execution & ExecutionTracer Telemetry.
"""

from __future__ import annotations

import asyncio
import time
import pytest

from nexusai.brain.plugins import ExtensionEvent, PluginFailurePolicy, PriorityExtensionDispatcher
from nexusai.brain.runtime import ExecutionContext, TurnChunk, TurnMetrics
from nexusai.brain.streaming import TurnStream
from nexusai.brain.telemetry import ExecutionTracer
from nexusai.core.errors import BrainError


def test_execution_tracer_timestamps_and_ttft() -> None:
    """Verify ExecutionTracer captures sub-stage latency milestones and calculates TTFT."""
    tracer = ExecutionTracer()
    time.sleep(0.01)  # Simulate network connect delay

    tracer.mark_provider_connected()
    time.sleep(0.02)  # Simulate first token generation delay

    tracer.mark_first_chunk()
    time.sleep(0.01)  # Simulate streaming duration

    tracer.output_tokens = 50
    tracer.mark_last_chunk()

    metrics = tracer.finalize_metrics()

    assert isinstance(metrics, TurnMetrics)
    assert metrics.ttft_ms >= 20.0  # TTFT should capture ~30ms
    assert metrics.latency_ms >= metrics.ttft_ms
    assert metrics.tokens_per_second > 0.0
    assert metrics.output_tokens == 50


def test_execution_tracer_span_helper() -> None:
    """Verify OpenTelemetry span context manager helper execution."""
    tracer = ExecutionTracer()
    with tracer.span("test_span", attributes={"module": "brain"}):
        time.sleep(0.005)


@pytest.mark.asyncio
async def test_turn_stream_iteration_and_ttft() -> None:
    """Verify TurnStream async iterator yields chunks with zero double-buffering and captures TTFT."""
    async def mock_provider_chunks() -> asyncio.AsyncIterator[TurnChunk]:
        yield TurnChunk(delta="Hello", sequence=0)
        yield TurnChunk(delta=" world", sequence=1, finish_reason="stop")

    ctx = ExecutionContext()
    tracer = ExecutionTracer()
    stream = TurnStream(provider_stream=mock_provider_chunks(), context=ctx, tracer=tracer)

    collected_chunks: list[TurnChunk] = []
    async for chunk in stream:
        collected_chunks.append(chunk)

    assert len(collected_chunks) == 2
    assert stream.full_text == "Hello world"
    assert stream.chunk_count == 2
    assert tracer.first_chunk_time is not None
    assert tracer.last_chunk_time is not None


@pytest.mark.asyncio
async def test_turn_stream_cancellation_monitoring() -> None:
    """Verify TurnStream detects cancellation signal and aborts stream execution."""
    async def infinite_chunks() -> asyncio.AsyncIterator[TurnChunk]:
        yield TurnChunk(delta="Chunk 1", sequence=0)
        yield TurnChunk(delta="Chunk 2", sequence=1)

    ctx = ExecutionContext()
    tracer = ExecutionTracer()
    stream = TurnStream(provider_stream=infinite_chunks(), context=ctx, tracer=tracer)

    # Signal cancellation after first chunk
    async for chunk in stream:
        if chunk.sequence == 0:
            ctx.cancellation.is_cancelled = True
            with pytest.raises(BrainError, match="aborted by cancellation signal"):
                await stream.__aiter__().__anext__()
            break

    assert tracer.is_cancelled is True


@pytest.mark.asyncio
async def test_plugin_failure_policy_error_isolation() -> None:
    """Verify PluginFailurePolicy.CONTINUE_ON_ERROR isolates non-critical plugin errors."""
    dispatcher = PriorityExtensionDispatcher()
    plugin_log: list[str] = []

    async def failing_telemetry_plugin(event: ExtensionEvent) -> None:
        plugin_log.append("failing_telemetry_attempted")
        raise RuntimeError("Telemetry collector crashed")

    async def critical_audit_plugin(event: ExtensionEvent) -> None:
        plugin_log.append("critical_audit_executed")

    # Register failing plugin with CONTINUE_ON_ERROR policy
    dispatcher.register_handler(
        "test_event",
        failing_telemetry_plugin,
        priority=1,
        failure_policy=PluginFailurePolicy.CONTINUE_ON_ERROR,
    )
    # Register audit plugin with higher priority integer (executed second)
    dispatcher.register_handler(
        "test_event",
        critical_audit_plugin,
        priority=2,
        failure_policy=PluginFailurePolicy.STOP_ON_ERROR,
    )

    ctx = ExecutionContext()
    event = ExtensionEvent(event_name="test_event", context=ctx)

    # Dispatch should NOT raise RuntimeError because failure_policy=CONTINUE_ON_ERROR
    await dispatcher.dispatch(event)

    assert "failing_telemetry_attempted" in plugin_log
    assert "critical_audit_executed" in plugin_log
