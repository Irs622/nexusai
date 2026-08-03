"""Contract verification test suite for GeminiProvider using httpx mock transport."""

import pytest
import httpx

from nexusai.providers import (
    ChatMessage,
    ChatRequest,
    GeminiProvider,
    MessageRole,
)
from tests.contracts.conformance_reporter import generate_conformance_report
from tests.contracts.test_provider_contract import (
    verify_provider_api_contract,
    verify_provider_behavior_contract,
)


def _custom_gemini_transport(request: httpx.Request) -> httpx.Response:
    """Mock HTTP transport returning realistic Google Gemini REST responses."""
    url = str(request.url)
    if "generateContent" in url:
        body = {
            "candidates": [
                {
                    "content": {"parts": [{"text": "Gemini test response output"}], "role": "model"},
                    "finishReason": "STOP",
                    "index": 0,
                }
            ],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 15, "totalTokenCount": 25},
        }
        return httpx.Response(200, json=body)
    elif "embedContent" in url:
        body = {"embedding": {"values": [0.1, 0.2, 0.3, 0.4]}}
        return httpx.Response(200, json=body)
    elif "models" in url:
        body = {
            "models": [
                {"name": "models/gemini-1.5-flash", "displayName": "Gemini 1.5 Flash", "inputTokenLimit": 1000000},
                {"name": "models/gemini-1.5-pro", "displayName": "Gemini 1.5 Pro", "inputTokenLimit": 2000000},
            ]
        }
        return httpx.Response(200, json=body)

    return httpx.Response(404, json={"error": "Not Found"})


@pytest.mark.asyncio
async def test_gemini_provider_contract_suite() -> None:
    """Run full Level 1 API and Level 2 Behavior contract verification against GeminiProvider."""
    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(_custom_gemini_transport),
        base_url="https://generativelanguage.googleapis.com/v1beta",
    )
    provider = GeminiProvider(api_key="ai-gemini-test-key", http_client=mock_client)

    # 1. API Surface Contract Verification
    await verify_provider_api_contract(provider)

    # 2. Behavior Contract Verification
    await verify_provider_behavior_contract(provider)

    # 3. Automated Conformance Report Generation
    report = await generate_conformance_report(provider)
    assert report.compatibility_percentage == 100.0
    print(f"\n{report.summary()}")
