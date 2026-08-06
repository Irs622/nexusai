import pytest
pytestmark = pytest.mark.network
"""Canonical Semantic Equivalence Test Suite across all Provider Translators.

Verifies that OpenAITranslator, GeminiTranslator, AnthropicTranslator, and OllamaTranslator
consistently produce semantically equivalent canonical ChatResponse structures, ChatRequest
payload mappings, ToolCall normalizations, and Error Taxonomy mappings.
"""

import pytest

from nexusai.providers import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    MessageRole,
    ProviderRateLimitError,
    ToolCall,
    ToolSchema,
    Usage,
)
from nexusai.providers.translators import (
    AnthropicTranslator,
    CanonicalErrorMapper,
    GeminiTranslator,
    OllamaTranslator,
    OpenAITranslator,
)


@pytest.fixture
def translators():
    return {
        "openai": OpenAITranslator(),
        "gemini": GeminiTranslator(),
        "anthropic": AnthropicTranslator(),
        "ollama": OllamaTranslator(),
    }


def test_chat_request_semantic_equivalence(translators):
    """Verify all translators preserve essential request semantics (roles, messages, params)."""
    req = ChatRequest(
        messages=[
            ChatMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            ChatMessage(role=MessageRole.USER, content="Hello, world!"),
        ],
        model="test-model",
        max_tokens=1000,
    )

    for provider_name, translator in translators.items():
        payload = translator.from_canonical_request(req)
        assert isinstance(payload, dict), f"{provider_name} request payload is not a dict"

        # Verify role and message content presence across payloads
        if provider_name in ("openai", "anthropic", "ollama"):
            assert "messages" in payload
            assert len(payload["messages"]) >= 1
        elif provider_name == "gemini":
            assert "contents" in payload
            assert len(payload["contents"]) >= 1


def test_chat_response_semantic_equivalence(translators):
    """Verify raw vendor payloads produce semantically equivalent ChatResponse objects."""
    # 1. OpenAI / OpenRouter Raw Payload
    openai_raw = {
        "id": "gen-123",
        "model": "gpt-4o",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "completion_tokens_details": {"reasoning_tokens": 5},
        },
    }

    # 2. Gemini Raw Payload
    gemini_raw = {
        "candidates": [{"content": {"parts": [{"text": "Hello!"}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 20, "totalTokenCount": 30, "thinkingTokenCount": 5},
    }

    # 3. Anthropic Raw Payload
    anthropic_raw = {
        "id": "msg-123",
        "model": "claude-3-5-sonnet",
        "content": [{"type": "text", "text": "Hello!"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 20, "thinking_tokens": 5},
    }

    # 4. Ollama Raw Payload
    ollama_raw = {
        "model": "llama3",
        "message": {"role": "assistant", "content": "Hello!"},
        "done": True,
        "prompt_eval_count": 10,
        "eval_count": 20,
    }

    res_openai = translators["openai"].to_canonical_response(openai_raw, "openrouter")
    res_gemini = translators["gemini"].to_canonical_response(gemini_raw, "gemini")
    res_anthropic = translators["anthropic"].to_canonical_response(anthropic_raw, "anthropic")
    res_ollama = translators["ollama"].to_canonical_response(ollama_raw, "ollama")

    responses = [res_openai, res_gemini, res_anthropic, res_ollama]

    # Verify Semantic Equivalence across canonical fields
    for res in responses:
        assert isinstance(res, ChatResponse)
        choice = res.primary_choice()
        assert choice.message.content == "Hello!"
        assert choice.message.role == MessageRole.ASSISTANT
        assert res.usage.prompt_tokens == 10
        assert res.usage.completion_tokens == 20
        assert res.usage.total_tokens == 30

    # Verify reasoning tokens mapping (explicit metrics on OpenAI, Gemini, Anthropic; 0 on Ollama)
    assert res_openai.usage.reasoning_tokens == 5
    assert res_gemini.usage.reasoning_tokens == 5
    assert res_anthropic.usage.reasoning_tokens == 5
    assert res_ollama.usage.reasoning_tokens == 0  # Ollama eval_count is NOT mapped as reasoning


def test_tool_call_semantic_equivalence(translators):
    """Verify tool call normalizations produce equivalent canonical ToolCall structures."""
    # OpenAI raw tool call
    openai_tc = translators["openai"].normalize_tool_calls(
        [{"id": "call_1", "function": {"name": "get_weather", "arguments": '{"city": "Jakarta"}'}}]
    )
    assert len(openai_tc) == 1
    assert openai_tc[0].name == "get_weather"
    assert openai_tc[0].arguments == {"city": "Jakarta"}

    # Anthropic raw tool use
    anthropic_tc = translators["anthropic"].normalize_tool_calls(
        [{"type": "tool_use", "id": "call_1", "name": "get_weather", "input": {"city": "Jakarta"}}]
    )
    assert len(anthropic_tc) == 1
    assert anthropic_tc[0].name == "get_weather"
    assert anthropic_tc[0].arguments == {"city": "Jakarta"}

    # Gemini raw function call
    gemini_tc = translators["gemini"].normalize_tool_calls(
        [{"functionCall": {"name": "get_weather", "args": {"city": "Jakarta"}}}]
    )
    assert len(gemini_tc) == 1
    assert gemini_tc[0].name == "get_weather"
    assert gemini_tc[0].arguments == {"city": "Jakarta"}


def test_error_mapper_retry_after_parsing():
    """Verify CanonicalErrorMapper extracts Retry-After header for RateLimit errors (seconds format)."""
    headers_sec = {"retry-after": "12.5", "content-type": "application/json"}
    err = CanonicalErrorMapper.map_http_error(429, "Rate limit exceeded", "openrouter", headers=headers_sec)
    assert isinstance(err, ProviderRateLimitError)
    assert err.retry_after == 12.5

    # Missing header defaults retry_after to None
    err_no_hdr = CanonicalErrorMapper.map_http_error(429, "Rate limit exceeded", "anthropic")
    assert isinstance(err_no_hdr, ProviderRateLimitError)
    assert err_no_hdr.retry_after is None


def test_error_mapper_retry_after_http_date():
    """Verify CanonicalErrorMapper handles RFC 1123 HTTP date strings in Retry-After headers."""
    # Future HTTP date string
    headers_date = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
    err = CanonicalErrorMapper.map_http_error(429, "Rate limit exceeded", "anthropic", headers=headers_date)
    assert isinstance(err, ProviderRateLimitError)
    assert err.retry_after is not None
    assert err.retry_after >= 0.0


def test_empty_response_handling(translators):
    """Verify translators handle empty or malformed vendor choices without crashing."""
    empty_openai = translators["openai"].to_canonical_response({}, "openrouter")
    assert isinstance(empty_openai, ChatResponse)
    assert len(empty_openai.choices) == 0

    empty_gemini = translators["gemini"].to_canonical_response({}, "gemini")
    assert isinstance(empty_gemini, ChatResponse)
    assert len(empty_gemini.choices) == 0

    empty_anthropic = translators["anthropic"].to_canonical_response({}, "anthropic")
    assert isinstance(empty_anthropic, ChatResponse)
    assert len(empty_anthropic.choices) == 1
    assert empty_anthropic.choices[0].message.content == ""
