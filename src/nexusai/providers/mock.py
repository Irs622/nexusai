"""Mock Provider adapter for testing, end-to-end validation, and Vertical Slice verification."""

from __future__ import annotations

from typing import Any, AsyncIterator

from nexusai.core.annotations import stable
from nexusai.providers.base import BaseProvider
from nexusai.providers.models import (
    Capability,
    CapabilityLevel,
    ChatChoice,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Embedding,
    EmbeddingResult,
    MessageRole,
    ModelInfo,
    ProviderCapabilities,
    ProviderHealth,
    ProviderMetadata,
    ProviderTrace,
    Usage,
)


@stable
class MockProvider(BaseProvider):
    """Mock Provider adapter providing deterministic responses for integration testing."""

    def __init__(
        self,
        provider_id: str = "mock_provider",
        display_name: str = "Mock Provider Adapter",
        healthy: bool = True,
        mock_response_text: str = "Mock response output",
        latency_ms: float = 5.0,
    ) -> None:
        self._provider_id = provider_id
        self._display_name = display_name
        self._healthy = healthy
        self.mock_response_text = mock_response_text
        self.latency_ms = latency_ms
        self.call_count = 0
        self.initialized = False
        self.shutdown_called = False

        caps = {
            Capability.CHAT: CapabilityLevel.NATIVE,
            Capability.STREAMING: CapabilityLevel.NATIVE,
            Capability.TOOLS: CapabilityLevel.ADVANCED,
            Capability.EMBEDDINGS: CapabilityLevel.BASIC,
        }
        self._capabilities = ProviderCapabilities(capabilities=caps)

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id=self._provider_id,
            display_name=self._display_name,
            homepage="https://nexusai.dev/mock",
            sdk_version="1.0.0",
            capabilities=self._capabilities,
        )

    async def initialize(self) -> None:
        self.initialized = True

    async def shutdown(self) -> None:
        self.shutdown_called = True

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.call_count += 1
        msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=self.mock_response_text,
        )
        choice = ChatChoice(index=0, message=msg, finish_reason="stop")
        usage = Usage(prompt_tokens=10, completion_tokens=15, total_tokens=25)
        trace = ProviderTrace(provider_id=self.id, latency_ms=self.latency_ms)
        return ChatResponse(
            choices=[choice],
            usage=usage,
            model=request.model or "mock-model-v1",
            provider=self.id,
            trace=trace,
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ChatResponse]:
        self.call_count += 1
        words = self.mock_response_text.split()
        for idx, word in enumerate(words):
            msg = ChatMessage(role=MessageRole.ASSISTANT, content=word + " ")
            choice = ChatChoice(index=0, message=msg)
            yield ChatResponse(
                choices=[choice], model=request.model or "mock-model-v1", provider=self.id
            )

    async def embeddings(
        self,
        texts: list[str],
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResult:
        self.call_count += 1
        embeds = [
            Embedding(text=t, vector=[0.01, 0.02, 0.03], index=i) for i, t in enumerate(texts)
        ]
        return EmbeddingResult(
            embeddings=embeds,
            model=model or "mock-embed-v1",
            provider=self.id,
            dimensions=3,
        )

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="mock-model-v1",
                display_name="Mock Model v1",
                supports_tools=True,
                supports_streaming=True,
            )
        ]

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            healthy=self._healthy,
            latency_ms=self.latency_ms,
            available_models=1,
        )
