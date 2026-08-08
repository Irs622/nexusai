"""
VectorRepository abstract contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from nexusai.memory.contracts.vector import VectorMatch


class VectorRepository(ABC):
    """Abstract repository interface for VectorStore operations."""

    @abstractmethod
    async def upsert_vector(
        self, embedding_id: str, vector: Sequence[float], metadata: dict[str, str] | None = None
    ) -> None:
        """Upsert a vector embedding into index."""
        pass

    @abstractmethod
    async def delete_vector(self, embedding_id: str) -> bool:
        """Remove a vector embedding by ID."""
        pass

    @abstractmethod
    async def search(self, query_vector: Sequence[float], top_k: int = 5) -> Sequence[VectorMatch]:
        """Perform similarity search."""
        pass
