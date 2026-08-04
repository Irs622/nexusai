"""
Enriched EmbeddingCapabilities value object and EmbeddingProvider abstract contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class EmbeddingCapabilities:
    """Enriched capabilities descriptor value object for embedding providers."""

    model_name: str
    dimensions: int
    max_batch: int = 64
    distance_metric: str = "cosine"
    normalized_output: bool = True
    supports_batch: bool = True
    supports_streaming: bool = False
    supports_async: bool = True
    max_input_tokens: int = 8192
    output_dtype: str = "float32"


class EmbeddingProvider(ABC):
    """Abstract contract for text embedding providers."""

    @property
    @abstractmethod
    def capabilities(self) -> EmbeddingCapabilities:
        """Return provider capabilities descriptor."""
        pass

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Generate vector embedding float list for input text."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate vector embeddings batch for multiple input texts."""
        pass
