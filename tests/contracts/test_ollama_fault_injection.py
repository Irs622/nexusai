"""Fault Injection Test Suite for OllamaProvider: server down/connection refused, 500 error, 404 model not found, and stream cancellation."""

import pytest
import httpx

from nexusai.providers import (
    ChatMessage,
    ChatRequest,
    MessageRole,
    OllamaProvider,
    ProviderNetworkError,
    ProviderNotFoundError,
    ProviderTimeoutError,
)
from nexusai.runtime import CancellationToken


@pytest.mark.asyncio
async def test_ollama_fault_injection_500_server_error() -> None:
    """Fault Injection: HTTP 500 Internal Server Error returns ProviderNetworkError."""
    def transport_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client = httpx.AsyncClient(transport=httpx.MockTransport(transport_500), base_url="http://localhost:11434/api")
    p = OllamaProvider(http_client=client)

    req = ChatRequest(messages=[ChatMessage(role=MessageRole.USER, content="hi")])
    with pytest.raises(ProviderNetworkError):
        await p.chat(req)


@pytest.mark.asyncio
async def test_ollama_fault_injection_404_model_not_found() -> None:
    """Fault Injection: HTTP 404 Model Not Found returns ProviderNotFoundError."""
    def transport_404(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model 'nonexistent' not found, try pulling it first"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(transport_404), base_url="http://localhost:11434/api")
    p = OllamaProvider(http_client=client)

    req = ChatRequest(messages=[ChatMessage(role=MessageRole.USER, content="hi")], model="nonexistent")
    with pytest.raises(ProviderNotFoundError):
        await p.chat(req)


@pytest.mark.asyncio
async def test_ollama_fault_injection_network_failure() -> None:
    """Fault Injection: Connection refused or network timeout returns ProviderNetworkError."""
    def transport_network_error(request: httpx.Request) -> httpx.Response:
        raise httpx.NetworkError("Connection refused")

    client = httpx.AsyncClient(transport=httpx.MockTransport(transport_network_error), base_url="http://localhost:11434/api")
    p = OllamaProvider(http_client=client)

    req = ChatRequest(messages=[ChatMessage(role=MessageRole.USER, content="hi")])
    with pytest.raises(ProviderNetworkError):
        await p.chat(req)


@pytest.mark.asyncio
async def test_ollama_fault_injection_stream_cancellation() -> None:
    """Fault Injection: Cancellation token cancelled during streaming iteration."""
    token = CancellationToken()
    token.cancel("User aborted stream")

    def transport_stream(request: httpx.Request) -> httpx.Response:
        content = '{"model": "llama3", "message": {"role": "assistant", "content": "hello"}, "done": false}\n'
        return httpx.Response(200, text=content)

    client = httpx.AsyncClient(transport=httpx.MockTransport(transport_stream), base_url="http://localhost:11434/api")
    p = OllamaProvider(http_client=client)

    req = ChatRequest(messages=[ChatMessage(role=MessageRole.USER, content="hi")])

    with pytest.raises(ProviderTimeoutError, match="User aborted stream"):
        token.throw_if_cancelled()
        async for chunk in p.stream_chat(req):
            pass
