"""Unit tests for interactive API key manager and provider detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexusai.cli.key_manager import detect_provider_from_key, save_key_to_env_file


@pytest.mark.unit
def test_detect_provider_from_key() -> None:
    """Verify auto-detection of provider, model, and base URL from key prefix."""
    # OpenRouter
    p, m, u = detect_provider_from_key("sk-or-v1-abcdef123456")
    assert p == "openrouter"
    assert m == "openrouter/auto"
    assert "openrouter.ai" in u

    # Groq
    p, m, u = detect_provider_from_key("gsk_mygroqsecretkey")
    assert p == "groq"
    assert "llama" in m
    assert "groq.com" in u

    # OpenAI
    p, m, u = detect_provider_from_key("sk-proj-myopenaikey")
    assert p == "openai"
    assert "gpt-4o" in m
    assert "openai.com" in u

    # Ollama offline
    p, m, u = detect_provider_from_key("ollama")
    assert p == "ollama"
    assert "localhost:11434" in u


@pytest.mark.unit
def test_save_key_to_env_file(tmp_path: Path) -> None:
    """Verify writing detected key to target .env file."""
    test_env = tmp_path / ".env"
    test_env.write_text("OPENAI_API_KEY=\nOPENROUTER_API_KEY=\n", encoding="utf-8")

    provider, model = save_key_to_env_file("gsk_testgroq123", env_path=test_env)
    assert provider == "groq"
    assert "llama" in model

    content = test_env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=gsk_testgroq123" in content
    assert "OPENAI_BASE_URL=https://api.groq.com/openai/v1" in content


@pytest.mark.unit
def test_prompt_and_configure_api_key_skips_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that when a key is already present, onboarding prompt is skipped."""
    from nexusai.cli.key_manager import prompt_and_configure_api_key

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-existing-active-key")
    # Should return immediately without asking for user input
    prompt_and_configure_api_key(interactive=True, force=False)

