"""Tests verifying that vendor translators correctly parse real payload JSON fixtures into canonical models."""

import json
from pathlib import Path
import pytest

from nexusai.providers.translators import (
    AnthropicTranslator,
    GeminiTranslator,
    OllamaTranslator,
    OpenAITranslator,
)


def _load_fixture(path_str: str) -> dict:
    p = Path(path_str)
    return json.loads(p.read_text())


def test_openai_translator_real_fixture() -> None:
    payload = _load_fixture("tests/fixtures/openrouter/chat.json")
    translator = OpenAITranslator()
    canonical = translator.to_canonical_response(payload, provider_id="openrouter")

    assert canonical.provider == "openrouter"
    assert canonical.primary_choice().message.content == "Hello from OpenRouter real payload fixture!"
    assert canonical.usage.total_tokens == 20


def test_gemini_translator_real_fixture() -> None:
    payload = _load_fixture("tests/fixtures/gemini/chat.json")
    translator = GeminiTranslator()
    canonical = translator.to_canonical_response(payload, provider_id="gemini")

    assert canonical.provider == "gemini"
    assert canonical.primary_choice().message.content == "Hello from Gemini real payload fixture!"
    assert canonical.usage.total_tokens == 25


def test_anthropic_translator_real_fixture() -> None:
    payload = _load_fixture("tests/fixtures/anthropic/chat.json")
    translator = AnthropicTranslator()
    canonical = translator.to_canonical_response(payload, provider_id="anthropic")

    assert canonical.provider == "anthropic"
    assert canonical.primary_choice().message.content == "Hello from Anthropic real payload fixture!"
    assert canonical.usage.total_tokens == 23


def test_ollama_translator_real_fixture() -> None:
    payload = _load_fixture("tests/fixtures/ollama/chat.json")
    translator = OllamaTranslator()
    canonical = translator.to_canonical_response(payload, provider_id="ollama")

    assert canonical.provider == "ollama"
    assert canonical.primary_choice().message.content == "Hello from Ollama local payload fixture!"
    assert canonical.usage.total_tokens == 22
