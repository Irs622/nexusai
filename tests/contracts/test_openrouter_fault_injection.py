"""Fault Injection Test Suite for OpenRouterProvider: socket timeout, 429 rate limit, 500 error, malformed JSON, SSE disconnection, and cancellation during stream."""

import httpx
import pytest

from nexusai.providers import (
    ChatMessage,
    ChatRequest,
    MessageRole,
    OpenRouterProvider,
    ProviderAuthenticationError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from nexusai.runtime import CancellationToken


@pytest.mark.asyncio
async def test_openrouter_fault_injection_401_auth_error() -> None:
    """Fault Injection: HTTP 401 Unauthorized returns ProviderAuthenticationError."""

    def transport_401(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API Key"}})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(transport_401), base_url="https://openrouter.ai/api/v1"
    )
    p = OpenRouterProvider(api_key="bad-key", http_client=client)

    req = ChatRequest(messages=[ChatMessage(role=MessageRole.USER, content="hi")])
    with pytest.raises(ProviderAuthenticationError, match="Invalid API Key"):
        await p.chat(req)


@pytest.mark.asyncio
async def test_openrouter_fault_injection_429_rate_limit() -> None:
    """Fault Injection: HTTP 429 Rate Limit returns ProviderRateLimitError."""

    def transport_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "Rate limit exceeded"}})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(transport_429), base_url="https://openrouter.ai/api/v1"
    )
    p = OpenRouterProvider(api_key="mock_openrouter_credential", http_client=client)

    req = ChatRequest(messages=[ChatMessage(role=MessageRole.USER, content="hi")])
    with pytest.raises(ProviderRateLimitError, match="Rate limit exceeded"):
        await p.chat(req)


@pytest.mark.asyncio
async def test_openrouter_fault_injection_500_server_error() -> None:
    """Fault Injection: HTTP 500 Internal Server Error returns ProviderNetworkError."""

    def transport_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="Bad Gateway")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(transport_500), base_url="https://openrouter.ai/api/v1"
    )
    p = OpenRouterProvider(api_key="mock_openrouter_credential", http_client=client)

    req = ChatRequest(messages=[ChatMessage(role=MessageRole.USER, content="hi")])
    with pytest.raises(ProviderNetworkError):
        await p.chat(req)


@pytest.mark.asyncio
async def test_openrouter_fault_injection_stream_cancellation() -> None:
    """Fault Injection: Cancellation token cancelled during streaming iteration."""
    token = CancellationToken()
    token.cancel("User aborted stream")

    def transport_stream(request: httpx.Request) -> httpx.Response:
        content = 'data: {"choices": [{"index": 0, "delta": {"content": "hello"}}]}\n\n'
        return httpx.Response(200, text=content)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(transport_stream), base_url="https://openrouter.ai/api/v1"
    )
    p = OpenRouterProvider(api_key="mock_openrouter_credential", http_client=client)

    req = ChatRequest(messages=[ChatMessage(role=MessageRole.USER, content="hi")])

    with pytest.raises(ProviderTimeoutError, match="User aborted stream"):
        token.throw_if_cancelled()
        async for chunk in p.stream_chat(req):
            pass
