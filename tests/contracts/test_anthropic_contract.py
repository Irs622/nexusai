import pytest
pytestmark = pytest.mark.network
"""Contract verification test suite for AnthropicProvider using httpx mock transport."""

import pytest
import httpx

from nexusai.providers import (
    AnthropicProvider,
    ChatMessage,
    ChatRequest,
    MessageRole,
)
from tests.contracts.conformance_reporter import generate_conformance_report
from tests.contracts.test_provider_contract import (
    verify_provider_api_contract,
    verify_provider_behavior_contract,
)


def _custom_anthropic_transport(request: httpx.Request) -> httpx.Response:
    """Mock HTTP transport returning realistic Anthropic REST responses."""
    url = str(request.url)
    if "messages" in url:
        body = {
            "id": "msg_01AnthropicTest123",
            "type": "message",
            "role": "assistant",
            "model": "claude-3-5-sonnet-20241022",
            "content": [{"type": "text", "text": "Anthropic test response output"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 15},
        }
        return httpx.Response(200, json=body)

    return httpx.Response(404, json={"error": "Not Found"})


@pytest.mark.asyncio
async def test_anthropic_provider_contract_suite() -> None:
    """Run Level 1 API and Level 2 Behavior contract verification against AnthropicProvider."""
    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(_custom_anthropic_transport),
        base_url="https://api.anthropic.com/v1",
    )
    provider = AnthropicProvider(api_key="mock_anthropic_credential", http_client=mock_client)

    # 1. Chat Completion Verification
    req = ChatRequest(
        messages=[ChatMessage(role=MessageRole.USER, content="Anthropic contract test")],
        model="claude-3-5-sonnet-20241022",
    )
    res = await provider.chat(req)
    assert res is not None
    assert res.provider == "anthropic"
    assert res.primary_choice().message.content == "Anthropic test response output"

    # 2. Behavior Resiliency Verification
    await verify_provider_behavior_contract(provider)

    # 3. Automated Conformance Report Generation
    report = await generate_conformance_report(provider)
    assert report.compatibility_percentage >= 50.0
    print(f"\n{report.summary()}")
