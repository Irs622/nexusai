"""Unit tests for Per-Provider CircuitBreaker metrics, Subprocess Output Truncation, and Streaming Runtime."""

import pytest

from nexusai.models.base import BaseModelProvider
from nexusai.models.circuit_breaker import CircuitBreaker
from nexusai.models.streaming import StreamingProviderRuntime
from nexusai.tools.isolation import SubprocessPluginRunner


class MockStreamProvider(BaseModelProvider):
    async def chat(self, messages: list, tools: list = None) -> dict:
        return {"type": "text", "content": "NexusAI streaming token output test"}


def test_circuit_breaker_per_provider_metrics() -> None:
    breaker = CircuitBreaker(
        provider_id="openai_gpt4", failure_threshold=2, recovery_timeout_seconds=60.0
    )
    breaker.record_failure(latency_ms=120.0)
    breaker.record_failure(latency_ms=150.0)

    metrics = breaker.get_metrics()
    assert metrics["provider_id"] == "openai_gpt4"
    assert metrics["state"] == "OPEN"
    assert metrics["total_failures"] == 2
    assert metrics["trip_count"] == 1
    assert metrics["success_ratio"] == 0.0
    assert metrics["avg_latency_ms"] == 135.0


@pytest.mark.asyncio
async def test_subprocess_output_truncation() -> None:
    runner = SubprocessPluginRunner(timeout_seconds=5.0, max_output_bytes=20)
    code = "print('A' * 100)"
    result = await runner.execute_isolated_code(code, {})
    assert result["truncated"] is True
    assert result["original_size"] > 20
    assert result["returned_size"] == 20


@pytest.mark.asyncio
async def test_streaming_provider_runtime() -> None:
    provider = MockStreamProvider()
    runtime = StreamingProviderRuntime(provider)
    chunks = []
    async for chunk in runtime.stream_chat([{"role": "user", "content": "Hi"}]):
        chunks.append(chunk)

    full_text = "".join(chunks).strip()
    assert full_text == "NexusAI streaming token output test"
