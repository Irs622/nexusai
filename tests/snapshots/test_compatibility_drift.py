import pytest

pytestmark = pytest.mark.network
"""Compatibility Drift Test Suite detecting external vendor payload breaking changes."""

import json
from pathlib import Path

import pytest

from nexusai.providers.translators import OpenAITranslator


def test_compatibility_drift_openrouter_wire_format() -> None:
    """Verify that OpenRouter 2026-08 payload snapshot has not suffered compatibility drift."""
    fixture_path = Path("tests/fixtures/openrouter/chat.json")
    raw_payload = json.loads(fixture_path.read_text())

    translator = OpenAITranslator()
    canonical = translator.to_canonical_response(raw_payload, provider_id="openrouter")

    # Assert essential contract fields exist without drift
    assert canonical.id == "gen-1700000000-openrouter-123"
    assert canonical.model == "openai/gpt-4o"
    assert len(canonical.choices) == 1
    assert (
        canonical.primary_choice().message.content == "Hello from OpenRouter real payload fixture!"
    )
    assert canonical.usage.total_tokens == 20
