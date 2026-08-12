"""Security verification test suite for P3-3 LLM Provider invariants (P3-3-INV-01 to P3-3-INV-10)."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.llm import (
    LLMAuthenticationError,
    LLMError,
    LLMMessage,
    LLMProviderUnavailableError,
    LLMRequest,
    LLMRole,
    LLMTimeoutError,
)
from nexusai.brain.runtime.llm_provider_registry import LLMProviderRegistry
from nexusai.infrastructure.llm.mock_provider import MockLLMProvider
from nexusai.infrastructure.llm.openai_provider import OpenAIProvider


@pytest.mark.asyncio
async def test_security_credential_isolation_and_redaction() -> None:
    """Security Test (P3-3-INV-01 & P3-3-INV-02): API keys and raw credentials NEVER leak into LLMResponse or metadata."""
    msg = LLMMessage(role=LLMRole.USER, content="Hello")
    req = LLMRequest(
        model="gpt-4o",
        messages=(msg,),
        metadata={"auth_header": "Bearer sk-proj-123456789"},
    )

    # Invariant: metadata attribute redacted sk-proj-123456789
    assert req.metadata["auth_header"] == "[REDACTED_SECRET]"

    provider = MockLLMProvider(name="sec-mock")
    resp = await provider.complete(req)

    # Invariant: Response string representation contains no credentials
    resp_str = str(resp)
    assert "sk-proj" not in resp_str
    assert "123456789" not in resp_str


@pytest.mark.asyncio
async def test_security_vendor_exception_normalization() -> None:
    """Security Test (P3-3-INV-03 & P3-3-INV-06): Vendor exceptions normalized into LLMError taxonomy."""
    # OpenAIProvider without API key raises LLMAuthenticationError (not raw KeyError or ValueError)
    provider = OpenAIProvider(api_key_env="NON_EXISTENT_KEY_ENV_XYZ")
    msg = LLMMessage(role=LLMRole.USER, content="Hello")
    req = LLMRequest(model="gpt-4o", messages=(msg,))

    with pytest.raises(LLMAuthenticationError):
        await provider.complete(req)

    # Mock timeout raises LLMTimeoutError
    mock_timeout = MockLLMProvider(failure_mode="timeout")
    with pytest.raises(LLMTimeoutError):
        await mock_timeout.complete(req)


@pytest.mark.asyncio
async def test_security_registry_duplicate_and_unknown_rejection() -> None:
    """Security Test (P3-3-INV-08 & P3-3-INV-09): Unknown provider lookup rejected, duplicate registration blocked."""
    registry = LLMProviderRegistry()
    p1 = MockLLMProvider(name="provider-sec")
    await registry.register(p1)

    with pytest.raises(ValueError, match="already registered"):
        await registry.register(p1)

    with pytest.raises(LLMProviderUnavailableError):
        await registry.resolve("non_existent_provider")


if __name__ == "__main__":
    asyncio.run(test_security_credential_isolation_and_redaction())
    asyncio.run(test_security_vendor_exception_normalization())
    asyncio.run(test_security_registry_duplicate_and_unknown_rejection())
    print("ALL P3-3 LLM PROVIDER SECURITY TESTS PASSED SUCCESSFULLY!")
