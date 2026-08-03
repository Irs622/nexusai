"""Shared Translator Contract Test Suite verifying BaseTranslator compliance across all translator implementations."""

from typing import Any
import pytest

from nexusai.providers import ChatMessage, ChatRequest, MessageRole
from nexusai.providers.translators import (
    AnthropicTranslator,
    BaseTranslator,
    GeminiTranslator,
    OllamaTranslator,
    OpenAITranslator,
)


def verify_translator_contract(translator: BaseTranslator) -> None:
    """Verify that a BaseTranslator instance satisfies standard translation contract rules."""
    req = ChatRequest(messages=[ChatMessage(role=MessageRole.USER, content="Contract test message")])

    # 1. from_canonical_request returns dictionary payload
    payload = translator.from_canonical_request(req)
    assert isinstance(payload, dict)
    assert len(payload) > 0

    # 2. normalize_tool_calls handles empty or invalid inputs cleanly
    normalized = translator.normalize_tool_calls(None)
    assert isinstance(normalized, list)
    assert len(normalized) == 0


def test_all_translators_contract() -> None:
    """Run shared translator contract suite across all implemented vendor translators."""
    translators = [
        OpenAITranslator(),
        AnthropicTranslator(),
        GeminiTranslator(),
        OllamaTranslator(),
    ]
    for t in translators:
        verify_translator_contract(t)
