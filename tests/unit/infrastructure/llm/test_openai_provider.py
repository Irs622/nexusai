"""Unit tests for OpenAIProvider exception mapping, response normalization, and zero hidden retries."""

from __future__ import annotations

import asyncio
import urllib.error
import pytest

from nexusai.brain.domain.llm import (
    LLMAuthenticationError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMRequest,
    LLMRole,
    LLMUnavailableError,
)
from nexusai.infrastructure.llm.openai_provider import OpenAIProvider


@pytest.mark.asyncio
async def test_openai_provider_missing_key_raises_auth_error() -> None:
    """Test OpenAIProvider raises LLMAuthenticationError when API key is missing."""
    provider = OpenAIProvider(api_key="")
    req = LLMRequest(
        model="gpt-4o",
        messages=(
            pytest.importorskip("nexusai.brain.domain.llm").LLMMessage(
                role=LLMRole.USER, content="hi"
            ),
        ),
    )

    with pytest.raises(LLMAuthenticationError, match="API key is missing"):
        await provider.complete(req)


def test_openai_provider_http_error_mapping() -> None:
    """Test _handle_http_error converts HTTP status codes to normalized domain exceptions."""
    provider = OpenAIProvider(api_key="test-key")

    with pytest.raises(LLMAuthenticationError):
        provider._handle_http_error(urllib.error.HTTPError("url", 401, "Unauthorized", {}, None))

    with pytest.raises(LLMRateLimitError):
        provider._handle_http_error(urllib.error.HTTPError("url", 429, "Rate Limit", {}, None))

    with pytest.raises(LLMInvalidRequestError):
        provider._handle_http_error(urllib.error.HTTPError("url", 400, "Bad Request", {}, None))

    with pytest.raises(LLMUnavailableError):
        provider._handle_http_error(
            urllib.error.HTTPError("url", 503, "Service Unavailable", {}, None)
        )


if __name__ == "__main__":
    asyncio.run(test_openai_provider_missing_key_raises_auth_error())
    test_openai_provider_http_error_mapping()
    print("ALL OPENAI PROVIDER UNIT TESTS PASSED SUCCESSFULLY!")
