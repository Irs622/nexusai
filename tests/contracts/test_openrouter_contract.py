import pytest

pytestmark = pytest.mark.network
"""Contract verification test suite for OpenRouterProvider using httpx mock transport."""

import httpx
import pytest

from nexusai.providers import (
    OpenRouterProvider,
)
from tests.contracts.conformance_reporter import generate_conformance_report
from tests.contracts.test_provider_contract import (
    verify_provider_api_contract,
    verify_provider_behavior_contract,
)


def _custom_transport(request: httpx.Request) -> httpx.Response:
    """Mock HTTP transport returning realistic OpenRouter REST responses."""
    url = str(request.url)
    if url.endswith("/chat/completions"):
        body = {
            "id": "gen-1700000099-openrouter",
            "model": "openai/gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "OpenRouter test response"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22},
        }
        return httpx.Response(200, json=body)
    elif url.endswith("/embeddings"):
        body = {"data": [{"embedding": [0.1, 0.2, 0.3], "index": 0}]}
        return httpx.Response(200, json=body)
    elif url.endswith("/models"):
        body = {
            "data": [
                {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "context_length": 128000},
                {
                    "id": "anthropic/claude-3.5-sonnet",
                    "name": "Claude 3.5 Sonnet",
                    "context_length": 200000,
                },
            ]
        }
        return httpx.Response(200, json=body)

    return httpx.Response(404, json={"error": "Not Found"})


@pytest.mark.asyncio
async def test_openrouter_provider_contract_suite() -> None:
    """Run full Level 1 API and Level 2 Behavior contract verification against OpenRouterProvider."""
    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(_custom_transport), base_url="https://openrouter.ai/api/v1"
    )
    provider = OpenRouterProvider(api_key="mock_openrouter_credential", http_client=mock_client)

    # 1. API Surface Contract Verification
    await verify_provider_api_contract(provider)

    # 2. Behavior Contract Verification
    await verify_provider_behavior_contract(provider)

    # 3. Automated Conformance Report Generation
    report = await generate_conformance_report(provider)
    assert report.compatibility_percentage == 100.0
    print(f"\n{report.summary()}")
