"""Abstract Base Class for LLM/Model Providers in NexusAI SDK."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from nexusai.core.annotations import stable
from nexusai.providers.models import (
    ChatRequest,
    ChatResponse,
    EmbeddingResult,
    ModelInfo,
    ProviderHealth,
    ProviderMetadata,
)


@stable
class BaseProvider(ABC):
    """Abstract base class for vendor-agnostic provider adapters."""

    @property
    @abstractmethod
    def metadata(self) -> ProviderMetadata:
        """Retrieve metadata describing provider identity and capabilities."""
        ...

    @property
    def id(self) -> str:
        """Convenience property returning the unique provider_id."""
        return self.metadata.provider_id

    async def describe(self) -> ProviderCapabilities:
        """Dynamically discover and return capabilities supported by this provider adapter."""
        return self.metadata.capabilities


    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Send a chat completion request to the provider.

        Args:
            request: Strongly-typed ChatRequest payload.

        Returns:
            Strongly-typed ChatResponse payload.
        """
        ...

    @abstractmethod
    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ChatResponse]:
        """Stream a chat completion response from the provider.

        Args:
            request: Strongly-typed ChatRequest payload.

        Yields:
            ChatResponse chunks as partial responses are generated.
        """
        if False:
            yield
        ...

    @abstractmethod
    async def embeddings(
        self,
        texts: list[str],
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResult:
        """Generate text embeddings for input strings.

        Args:
            texts: List of text strings to generate vector embeddings for.
            model: Optional model identifier.
            **kwargs: Additional provider parameters.

        Returns:
            Strongly-typed EmbeddingResult.
        """
        ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """List models supported by this provider.

        Returns:
            List of ModelInfo objects.
        """
        ...

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Perform a health check to verify provider reachability and status.

        Returns:
            ProviderHealth snapshot.
        """
        ...

    async def initialize(self) -> None:
        """Asynchronous lifecycle initialization hook for provider setup."""
        pass

    async def shutdown(self) -> None:
        """Asynchronous lifecycle cleanup hook for provider resource tear down."""
        pass

    async def __aenter__(self) -> BaseProvider:
        """Async context manager entry: initializes provider resources."""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit: shuts down provider resources."""
        await self.shutdown()
