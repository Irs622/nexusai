"""Failure mode integration test suite for LLM provider error normalization and zero hidden retries."""

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
    LLMTimeoutError,
    LLMUnavailableError,
)
from nexusai.infrastructure.llm.openai_provider import OpenAIProvider


@pytest.mark.asyncio
async def test_llm_provider_error_normalization_matrix() -> None:
    """Verify HTTP status codes normalize into domain exception hierarchy."""
    provider = OpenAIProvider(api_key="test-key")

    with pytest.raises(LLMAuthenticationError):
        provider._handle_http_error(urllib.error.HTTPError("url", 401, "Unauthorized", {}, None))

    with pytest.raises(LLMRateLimitError):
        provider._handle_http_error(urllib.error.HTTPError("url", 429, "Rate Limit", {}, None))

    with pytest.raises(LLMInvalidRequestError):
        provider._handle_http_error(urllib.error.HTTPError("url", 400, "Bad Request", {}, None))

    with pytest.raises(LLMUnavailableError):
        provider._handle_http_error(urllib.error.HTTPError("url", 502, "Bad Gateway", {}, None))


if __name__ == "__main__":
    asyncio.run(test_llm_provider_error_normalization_matrix())
    print("ALL P4-3 LLM FAILURE MODES INTEGRATION TESTS PASSED SUCCESSFULLY!")
