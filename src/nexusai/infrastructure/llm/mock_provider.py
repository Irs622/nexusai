"""MockLLMProvider deterministic testing adapter implementing ILLMProvider."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from nexusai.brain.domain.llm import (
    FinishReason,
    LLMAuthenticationError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMUsage,
)
from nexusai.brain.ports.llm_provider_port import ILLMProvider
from nexusai.brain.ports.observability_port import IObservabilityPort


class MockLLMProvider(ILLMProvider):
    """Deterministic MockLLMProvider for unit, integration, and security testing."""

    def __init__(
        self,
        name: str = "mock",
        default_response: str = "Mock model completion output",
        failure_mode: str | None = None,
        telemetry: IObservabilityPort | None = None,
    ) -> None:
        self._name = name
        self.default_response = default_response
        self.failure_mode = failure_mode
        self.telemetry = telemetry
        self.request_count: int = 0

    @property
    def provider_name(self) -> str:
        return self._name

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute model completion request and return normalized LLMResponse."""
        t0 = time.perf_counter()
        self.request_count += 1

        # Simulate failure modes
        if self.failure_mode == "timeout":
            await asyncio.sleep(0.01)
            raise LLMTimeoutError(f"Model request to provider '{self._name}' timed out after {request.timeout_seconds}s")
        elif self.failure_mode == "auth_error":
            raise LLMAuthenticationError(f"Invalid API Key for provider '{self._name}'")
        elif self.failure_mode == "rate_limit":
            raise LLMRateLimitError(f"Rate limit exceeded for provider '{self._name}'")
        elif self.failure_mode == "invalid_request":
            raise LLMInvalidRequestError(f"Invalid request parameters for model '{request.model}'")

        # Simulate execution latency
        await asyncio.sleep(0.005)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        prompt_toks = sum(len(m.content.split()) for m in request.messages)
        compl_toks = len(self.default_response.split())

        return LLMResponse(
            provider=self._name,
            model=request.model,
            content=self.default_response,
            finish_reason=FinishReason.STOP,
            usage=LLMUsage(
                prompt_tokens=prompt_toks,
                completion_tokens=compl_toks,
                total_tokens=prompt_toks + compl_toks,
            ),
            request_id=f"req-mock-{self.request_count}",
            latency_ms=latency_ms,
        )
