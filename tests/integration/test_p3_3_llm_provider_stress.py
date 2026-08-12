"""Adversarial stress test suite for P3-3 LLM Provider concurrency safety and failure modes."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.llm import (
    LLMError,
    LLMMessage,
    LLMRateLimitError,
    LLMRequest,
    LLMRole,
    LLMTimeoutError,
)
from nexusai.brain.runtime.llm_provider_registry import LLMProviderRegistry
from nexusai.infrastructure.llm.mock_provider import MockLLMProvider


@pytest.mark.asyncio
async def test_p3_3_adversarial_provider_stress() -> None:
    """Stress Test: 20+ concurrent completion requests across mock providers under timeouts and rate-limit faults."""
    registry = LLMProviderRegistry()

    provider_normal = MockLLMProvider(name="mock-normal")
    provider_flaky = MockLLMProvider(name="mock-flaky", failure_mode="rate_limit")
    provider_timeout = MockLLMProvider(name="mock-timeout", failure_mode="timeout")

    await registry.register(provider_normal)
    await registry.register(provider_flaky)
    await registry.register(provider_timeout)

    msg = LLMMessage(role=LLMRole.USER, content="Stress request")
    req = LLMRequest(model="gpt-4o", messages=(msg,))

    async def worker(worker_id: int) -> None:
        p_name = "mock-normal" if worker_id % 3 == 0 else ("mock-flaky" if worker_id % 3 == 1 else "mock-timeout")
        p = await registry.resolve(p_name)

        if p_name == "mock-normal":
            resp = await p.complete(req)
            assert resp.content == "Mock model completion output"
            assert resp.provider == "mock-normal"
        elif p_name == "mock-flaky":
            with pytest.raises(LLMRateLimitError):
                await p.complete(req)
        elif p_name == "mock-timeout":
            with pytest.raises(LLMTimeoutError):
                await p.complete(req)

    # Launch 30 concurrent workers executing requests
    workers = [asyncio.create_task(worker(w)) for w in range(30)]
    await asyncio.gather(*workers)

    print(f"\n[P3-3 ADVERSARIAL LLM PROVIDER STRESS VERIFICATION]")
    print(f"Total Completed Provider Requests: {provider_normal.request_count}")
    assert provider_normal.request_count == 10, "10 normal requests must succeed cleanly"


if __name__ == "__main__":
    asyncio.run(test_p3_3_adversarial_provider_stress())
    print("ALL P3-3 LLM PROVIDER INTEGRATION & STRESS TESTS PASSED SUCCESSFULLY!")
