"""Canonical Normalization and Snapshot Tests for Provider SDK payloads."""

import pytest

from nexusai.providers import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    MessageRole,
    MockProvider,
)


@pytest.mark.asyncio
async def test_canonical_normalization_snapshot() -> None:
    """Verify that MockProvider output matches canonical normalized structure."""
    mock_p = MockProvider(
        provider_id="snap_mock",
        mock_response_text="Canonical normalized text",
    )
    req = ChatRequest(
        messages=[ChatMessage(role=MessageRole.USER, content="Hello snap")],
        model="mock-v1",
    )
    response = await mock_p.chat(req)

    # 1. Canonical structure assertions
    assert isinstance(response, ChatResponse)
    assert response.provider == "snap_mock"
    assert response.model == "mock-v1"

    primary = response.primary_choice()
    assert primary.index == 0
    assert primary.message.role == MessageRole.ASSISTANT
    assert primary.message.content == "Canonical normalized text"
    assert primary.finish_reason == "stop"

    # 2. Canonical Usage snapshot
    assert response.usage is not None
    assert response.usage.prompt_tokens == 10
    assert response.usage.completion_tokens == 15
    assert response.usage.total_tokens == 25

    # 3. Canonical Trace snapshot
    assert response.trace is not None
    assert response.trace.provider_id == "snap_mock"
    assert response.trace.latency_ms > 0
