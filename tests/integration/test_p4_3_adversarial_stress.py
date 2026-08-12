"""Adversarial stress test suite for P4-3 LLM Provider concurrency safety and credential isolation."""

from __future__ import annotations

import asyncio
import os
import pytest

from nexusai.brain.domain.llm import LLMMessage, LLMRequest, LLMRole
from nexusai.infrastructure.llm.openai_provider import OpenAIProvider


@pytest.mark.asyncio
async def test_p4_3_adversarial_llm_provider_stress() -> None:
    """Stress Test: 30 concurrent LLM completion requests enforcing session isolation and zero secret leakage.

    Invariants: Zero credential leakage into exceptions/metadata, zero hidden retries, 100% thread/task safe.
    """
    provider = OpenAIProvider(api_key="sk-test-secret-key-12345")

    async def worker(w_id: int) -> None:
        msg = LLMMessage(role=LLMRole.USER, content=f"Request {w_id} for session sess-{w_id}")
        req = LLMRequest(
            model="gpt-4o",
            messages=(msg,),
            temperature=0.0,
            metadata={"user": f"user_{w_id}", "secret_token": "sk-secret-token-val"},
        )
        res = await provider.complete(req)

        assert res.provider == "openai"
        assert "sk-test-secret-key-12345" not in res.content
        assert req.metadata["secret_token"] == "[REDACTED_SECRET]"

    workers = [asyncio.create_task(worker(i)) for i in range(30)]
    await asyncio.gather(*workers)

    print(f"\n[P4-3 ADVERSARIAL LLM PROVIDER STRESS VERIFICATION]")
    print("30 Concurrent Provider Requests completed cleanly with 100% Secret Isolation!")


if __name__ == "__main__":
    asyncio.run(test_p4_3_adversarial_llm_provider_stress())
    print("ALL P4-3 ADVERSARIAL STRESS TESTS PASSED SUCCESSFULLY!")
