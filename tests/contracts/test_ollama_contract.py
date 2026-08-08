"""Contract verification test suite for OllamaProvider using httpx mock transport."""

import httpx
import pytest

from nexusai.providers import (
    ChatMessage,
    ChatRequest,
    MessageRole,
    OllamaProvider,
)
from tests.contracts.conformance_reporter import generate_conformance_report
from tests.contracts.test_provider_contract import (
    verify_provider_behavior_contract,
)


def _custom_ollama_transport(request: httpx.Request) -> httpx.Response:
    """Mock HTTP transport returning realistic Ollama REST responses."""
    url = str(request.url)

    if "chat" in url:
        body = {
            "model": "llama3",
            "message": {
                "role": "assistant",
                "content": "Ollama test response output",
            },
            "done": True,
            "prompt_eval_count": 10,
            "eval_count": 15,
        }
        return httpx.Response(200, json=body)

    elif "tags" in url:
        body = {"models": [{"name": "llama3:latest", "model": "llama3:latest"}]}
        return httpx.Response(200, json=body)

    return httpx.Response(404, json={"error": "Not Found"})


@pytest.mark.asyncio
async def test_ollama_provider_contract_suite() -> None:
    """Run Level 1 API and Level 2 Behavior contract verification against OllamaProvider."""
    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(_custom_ollama_transport),
        base_url="http://localhost:11434/api",
    )
    provider = OllamaProvider(http_client=mock_client)

    # 1. Chat Completion Verification
    req = ChatRequest(
        messages=[ChatMessage(role=MessageRole.USER, content="Ollama contract test")],
        model="llama3",
    )
    res = await provider.chat(req)
    assert res is not None
    assert res.provider == "ollama"
    assert res.primary_choice().message.content == "Ollama test response output"

    # 2. Behavior Resiliency Verification
    await verify_provider_behavior_contract(provider)

    # 3. Automated Conformance Report Generation
    report = await generate_conformance_report(provider)
    assert report.compatibility_percentage >= 50.0
    print(f"\n{report.summary()}")
