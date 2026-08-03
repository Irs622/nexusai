"""Live API Integration Test Suite for OpenRouterProvider (requires OPENROUTER_API_KEY)."""

import os
import pytest

from nexusai.providers import (
    ChatMessage,
    ChatRequest,
    MessageRole,
    OpenRouterProvider,
)
from nexusai.runtime import ExecutionEngine


@pytest.mark.skipif(not os.getenv("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY environment variable not set")
@pytest.mark.asyncio
async def test_openrouter_live_api_chat_completion() -> None:
    """Live API Test: Send real chat completion request to OpenRouter API."""
    provider = OpenRouterProvider()
    engine = ExecutionEngine()
    engine.manager.registry.register(provider)

    req = ChatRequest(
        messages=[ChatMessage(role=MessageRole.USER, content="Reply with one word: Hello")],
        model="openai/gpt-4o-mini",
    )

    response = await engine.execute_chat(req)

    assert response is not None
    assert response.provider == "openrouter"
    assert len(response.choices) > 0
    primary = response.primary_choice()
    assert isinstance(primary.message.content, str)
    assert len(primary.message.content) > 0
    print(f"\nLive OpenRouter Output: {primary.message.content}")
