"""
MockEmbeddingProvider implementation for deterministic testing.
"""

from __future__ import annotations

from typing import Sequence

from nexusai.memory.contracts.embedding import EmbeddingCapabilities, EmbeddingProvider


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic MockEmbeddingProvider for testing."""

    def __init__(self, model_name: str = "mock-nomic-embed", dimensions: int = 768) -> None:
        self._capabilities = EmbeddingCapabilities(
            model_name=model_name,
            dimensions=dimensions,
            max_batch=32,
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
        """Generate deterministic float vector based on text hash."""
        val = (hash(text) % 1000) / 1000.0
        return [val] * self._capabilities.dimensions

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate batch deterministic vectors."""
        return [await self.embed_text(t) for t in texts]
