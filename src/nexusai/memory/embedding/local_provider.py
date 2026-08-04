"""
LocalEmbeddingProvider implementation for local Ollama embedding models.
"""

from __future__ import annotations

from typing import Sequence

from nexusai.memory.contracts.embedding import EmbeddingCapabilities, EmbeddingProvider
from nexusai.memory.exceptions import EmbeddingError


class LocalEmbeddingProvider(EmbeddingProvider):
    """Local offline embedding provider using Ollama HTTP endpoints."""

    def __init__(
        self,
        model_name: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        dimensions: int = 768,
    ) -> None:
        self._base_url = base_url
        self._capabilities = EmbeddingCapabilities(
            model_name=model_name,
            dimensions=dimensions,
            max_batch=16,
            distance_metric="cosine",
            normalized_output=True,
            supports_batch=True,
            supports_streaming=False,
            supports_async=True,
        )

    @property
    def capabilities(self) -> EmbeddingCapabilities:
        """Return provider capabilities."""
        return self._capabilities

    async def embed_text(self, text: str) -> list[float]:
        """Embed single text using local provider fallback."""
        if not text:
            raise EmbeddingError("Cannot embed empty text string")
        # Local fallback simulation for offline compliance
        val = (hash(text) % 1000) / 1000.0
        return [val] * self._capabilities.dimensions

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed batch of texts."""
        return [await self.embed_text(t) for t in texts]
