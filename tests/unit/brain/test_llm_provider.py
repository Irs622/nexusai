"""Unit test suite for LLM domain models, LLMRequest validation, and LLMResponse metrics."""

from __future__ import annotations

import pytest

from nexusai.brain.domain.llm import (
    FinishReason,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMRole,
    LLMUsage,
)


def test_llm_request_domain_validation_and_secret_redaction() -> None:
    """Test LLMRequest domain invariants and metadata secret redaction."""
    msg = LLMMessage(role=LLMRole.USER, content="Hello LLM")
    req = LLMRequest(
        model="gpt-4o",
        messages=(msg,),
        temperature=0.2,
        max_tokens=1000,
        metadata={"user": "alice", "api_key": "secret-12345"},
    )

    assert req.model == "gpt-4o"
    assert req.messages[0].content == "Hello LLM"
    assert req.metadata["user"] == "alice"
    assert req.metadata["api_key"] == "[REDACTED_SECRET]"

    with pytest.raises(ValueError, match="model cannot be empty"):
        LLMRequest(model="  ", messages=(msg,))

    with pytest.raises(ValueError, match="messages tuple cannot be empty"):
        LLMRequest(model="gpt-4o", messages=())


def test_llm_response_domain_model() -> None:
    """Test LLMResponse structure and usage token counts."""
    usage = LLMUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    resp = LLMResponse(
        provider="openai",
        model="gpt-4o",
        content="Generated content",
        finish_reason=FinishReason.STOP,
        usage=usage,
        request_id="resp-123",
        latency_ms=120.5,
    )

    assert resp.provider == "openai"
    assert resp.content == "Generated content"
    assert resp.usage.total_tokens == 150
    assert resp.finish_reason == FinishReason.STOP


if __name__ == "__main__":
    test_llm_request_domain_validation_and_secret_redaction()
    test_llm_response_domain_model()
    print("ALL LLM DOMAIN UNIT TESTS PASSED SUCCESSFULLY!")
