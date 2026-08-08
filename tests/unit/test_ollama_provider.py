"""Unit tests for OllamaProvider adapter using httpx mock transport."""

import httpx
import pytest

from nexusai.providers import (
    Capability,
    ChatMessage,
    ChatRequest,
    MessageRole,
    OllamaProvider,
)


def _mock_ollama_transport(request: httpx.Request) -> httpx.Response:
    """Mock HTTP transport returning realistic Ollama REST responses."""
    url = str(request.url)

    if "/chat" in url:
        body = {
            "model": "llama3",
            "created_at": "2026-08-04T00:00:00Z",
            "message": {
                "role": "assistant",
                "content": "Hello from Ollama local test!",
            },
            "done": True,
            "total_duration": 500000000,
            "load_duration": 100000000,
            "prompt_eval_count": 12,
            "eval_count": 8,
        }
        return httpx.Response(200, json=body)

    elif "/embed" in url or "/embeddings" in url:
        body = {
            "model": "llama3",
            "embeddings": [[0.1, 0.2, 0.3]],
        }
        return httpx.Response(200, json=body)

    elif "/tags" in url:
        body = {
            "models": [
                {
                    "name": "llama3:latest",
                    "model": "llama3:latest",
                    "details": {"family": "llama"},
                },
                {
                    "name": "qwen2.5:coder",
                    "model": "qwen2.5:coder",
                    "details": {"family": "qwen2"},
                },
            ]
        }
        return httpx.Response(200, json=body)

    return httpx.Response(404, json={"error": "Not Found"})


@pytest.mark.asyncio
async def test_ollama_provider_metadata() -> None:
    provider = OllamaProvider()
    assert provider.id == "ollama"
    assert provider.metadata.display_name == "Ollama Local Engine"
    assert provider.metadata.capabilities.supports(Capability.CHAT)


@pytest.mark.asyncio
async def test_ollama_provider_chat() -> None:
    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(_mock_ollama_transport),
        base_url="http://localhost:11434/api",
    )
    provider = OllamaProvider(http_client=mock_client)

    req = ChatRequest(
        messages=[ChatMessage(role=MessageRole.USER, content="Hello Ollama")],
        model="llama3",
    )
    res = await provider.chat(req)

    assert res is not None
    assert res.provider == "ollama"
    assert res.primary_choice().message.content == "Hello from Ollama local test!"
    assert res.usage.prompt_tokens == 12
    assert res.usage.completion_tokens == 8


@pytest.mark.asyncio
async def test_ollama_provider_stream_chat() -> None:
    def streaming_transport(request: httpx.Request) -> httpx.Response:
        lines = (
            '{"model": "llama3", "message": {"role": "assistant", "content": "Hello "}, "done": false}\n'
            '{"model": "llama3", "message": {"role": "assistant", "content": "world!"}, "done": true, "prompt_eval_count": 5, "eval_count": 2}\n'
        )
        return httpx.Response(200, text=lines)

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(streaming_transport),
        base_url="http://localhost:11434/api",
    )
    provider = OllamaProvider(http_client=mock_client)

    req = ChatRequest(messages=[ChatMessage(role=MessageRole.USER, content="Stream test")])
    chunks = []
    async for chunk in provider.stream_chat(req):
        chunks.append(chunk.primary_choice().message.content)

    assert "".join(chunks) == "Hello world!"


@pytest.mark.asyncio
async def test_ollama_provider_embeddings() -> None:
    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(_mock_ollama_transport),
        base_url="http://localhost:11434/api",
    )
    provider = OllamaProvider(http_client=mock_client)

    res = await provider.embeddings(["test text"], model="llama3")
    assert len(res.embeddings) == 1
    assert res.embeddings[0].vector == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_ollama_provider_list_models() -> None:
    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(_mock_ollama_transport),
        base_url="http://localhost:11434/api",
    )
    provider = OllamaProvider(http_client=mock_client)

    models = await provider.list_models()
    assert len(models) == 2
    assert models[0].id == "llama3:latest"
    assert models[1].id == "qwen2.5:coder"


@pytest.mark.asyncio
async def test_ollama_provider_health_check() -> None:
    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(_mock_ollama_transport),
        base_url="http://localhost:11434/api",
    )
    provider = OllamaProvider(http_client=mock_client)

    health = await provider.health_check()
    assert health.healthy is True
    assert health.available_models == 2


@pytest.mark.asyncio
async def test_ollama_provider_context_manager() -> None:
    async with OllamaProvider() as p:
        assert p._client is not None
    assert p._client is None
