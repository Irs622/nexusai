"""Live API Integration Test Suite for OllamaProvider (requires local Ollama server running at http://localhost:11434)."""

import os

import httpx
import pytest

from nexusai.providers import (
    ChatMessage,
    ChatRequest,
    MessageRole,
    OllamaProvider,
)
from nexusai.runtime import ExecutionEngine


def _is_ollama_online() -> bool:
    """Check if local Ollama server is running and accessible."""
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api")
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/tags", timeout=1.5)
        return resp.status_code == 200
    except Exception:
        return False


OLLAMA_AVAILABLE = _is_ollama_online()


@pytest.mark.skipif(
    not OLLAMA_AVAILABLE, reason="Local Ollama server (http://localhost:11434) is not running"
)
@pytest.mark.asyncio
async def test_ollama_live_api_chat_completion() -> None:
    """Live API Test: Send real chat completion request to local Ollama server."""
    provider = OllamaProvider()
    engine = ExecutionEngine()
    engine.manager.registry.register(provider)

    req = ChatRequest(
        messages=[ChatMessage(role=MessageRole.USER, content="Reply with one word: Hello")],
        model="llama3",
    )

    response = await engine.execute_chat(req)

    assert response is not None
    assert response.provider == "ollama"
    assert len(response.choices) > 0
    primary = response.primary_choice()
    assert isinstance(primary.message.content, str)
    assert len(primary.message.content) > 0
    print(f"\nLive Ollama Output: {primary.message.content}")
