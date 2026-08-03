"""Benchmark verifying that ExecutionEngine runtime overhead stays below 2.0ms."""

import time
import pytest

from nexusai.providers import ChatMessage, ChatRequest, MessageRole, MockProvider
from nexusai.runtime import ExecutionEngine


@pytest.mark.asyncio
async def test_execution_engine_runtime_overhead_benchmark() -> None:
    """Verify ExecutionEngine framework overhead is < 2.0ms per request execution."""
    mock_p = MockProvider("overhead_mock")
    engine = ExecutionEngine()
    engine.manager.registry.register(mock_p)

    req = ChatRequest(messages=[ChatMessage(role=MessageRole.USER, content="Benchmark message")])

    # Warmup
    for _ in range(5):
        await engine.execute_chat(req)

    # Measure 50 runs
    times: list[float] = []
    for _ in range(50):
        t0 = time.perf_counter()
        await engine.execute_chat(req)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000.0)

    times.sort()
    median_ms = times[len(times) // 2]
    print(f"\nExecutionEngine Median Overhead: {median_ms:.3f}ms (p95: {times[int(len(times)*0.95)]:.3f}ms)")

    assert median_ms < 2.0, f"ExecutionEngine overhead exceeded 2.0ms target: {median_ms:.3f}ms"
