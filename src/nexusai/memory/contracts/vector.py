"""
DistanceMetric, VectorCapabilities, VectorRecord, VectorMatch, and VectorStore ABC contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence


class DistanceMetric(str, Enum):
    """Distance metrics supported by vector stores."""

    COSINE = "cosine"
    DOT_PRODUCT = "dot_product"
    EUCLIDEAN = "euclidean"
    INNER_PRODUCT = "inner_product"


@dataclass(frozen=True)
class VectorCapabilities:
    """Capabilities descriptor value object for vector store backends."""

    provider_name: str
    dimensions: int
    supported_metrics: tuple[DistanceMetric, ...] = (DistanceMetric.COSINE,)
    supports_namespaces: bool = True
    supports_metadata_filtering: bool = True
    supports_batch: bool = True


@dataclass
class VectorRecord:
    """Vector record container for insertion into VectorStore."""

    record_id: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    namespace: str = "default"
    payload: str | None = None


@dataclass(frozen=True)
class VectorMatch:
    """Similarity search match result container."""

    record_id: str
    distance: float
    similarity: float
    metadata: dict[str, Any] = field(default_factory=dict)
    payload: str | None = None
    namespace: str = "default"
    provider_metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    """Abstract contract for vector database engines and adapters."""

    @property
    @abstractmethod
    def capabilities(self) -> VectorCapabilities:
        """Return provider capabilities descriptor."""
        pass

    @abstractmethod
    async def upsert(self, record: VectorRecord) -> None:
        """Upsert a single VectorRecord into the vector index."""
        pass

    @abstractmethod
    async def delete(self, record_id: str, namespace: str = "default") -> bool:
        """Delete a single vector record by ID within target namespace."""
        pass

    @abstractmethod
    async def get(self, record_id: str, namespace: str = "default") -> VectorRecord | None:
        """Get a single vector record by ID within target namespace."""
        pass

    @abstractmethod
    async def search(
        self,
        query_vector: Sequence[float],
        top_k: int = 5,
        namespace: str = "default",
        filter_dict: dict[str, Any] | None = None,
    ) -> Sequence[VectorMatch]:
        """Perform similarity search returning top_k matches within namespace."""
        pass

    @abstractmethod
    async def batch_upsert(self, records: Sequence[VectorRecord]) -> None:
        """Upsert a batch of VectorRecords."""
        pass

    @abstractmethod
    async def batch_delete(self, record_ids: Sequence[str], namespace: str = "default") -> int:
        """Delete a batch of vector records by ID returning count deleted."""
        pass

    @abstractmethod
    async def count(self, namespace: str = "default") -> int:
        """Count total vector records in namespace."""
        pass

    @abstractmethod
    async def clear(self, namespace: str = "default") -> None:
        """Clear all vector records in namespace."""
        pass

    async def health(self) -> dict[str, Any]:
        """Return health status dictionary."""
        return {
            "provider": self.capabilities.provider_name,
            "dimensions": self.capabilities.dimensions,
            "healthy": True,
        }
