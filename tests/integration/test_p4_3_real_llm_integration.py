"""Contract integration test suite for real LLM Provider adapters (supporting opt-in live test flag NEXUSAI_LIVE_LLM_TESTS=1)."""

from __future__ import annotations

import asyncio
import os
import pytest

from nexusai.brain.domain.llm import LLMMessage, LLMRequest, LLMRole
from nexusai.infrastructure.llm.openai_provider import OpenAIProvider


@pytest.mark.asyncio
async def test_openai_provider_contract_completion() -> None:
    """Test OpenAIProvider contract completion in deterministic simulation mode or opt-in live test mode."""
    api_key = os.getenv("OPENAI_API_KEY", "dummy-key-for-contract-test")
    provider = OpenAIProvider(api_key=api_key)

    msg = LLMMessage(role=LLMRole.USER, content="Generate plan for echo task")
    req = LLMRequest(model="gpt-4o", messages=(msg,), temperature=0.0)

    res = await provider.complete(req)

    assert res.provider == "openai"
    assert res.model == "gpt-4o"
    assert len(res.content) > 0
    assert res.usage is not None
    assert res.usage.total_tokens > 0


if __name__ == "__main__":
    asyncio.run(test_openai_provider_contract_completion())
    print("ALL REAL LLM CONTRACT INTEGRATION TESTS PASSED SUCCESSFULLY!")
