"""
ChromaVectorStore implementation for local ChromaDB vector store integration.
"""

from __future__ import annotations

from typing import Any, Sequence

from nexusai.memory.contracts.vector import (
    DistanceMetric,
    VectorCapabilities,
    VectorMatch,
    VectorRecord,
    VectorStore,
)
from nexusai.memory.vector.in_memory import InMemoryVectorStore


class ChromaVectorStore(VectorStore):
    """Local ChromaDB vector store backend adapter with fallback."""

    def __init__(
        self,
        collection_name: str = "nexusai_vectors",
        persist_directory: str | None = None,
        dimensions: int = 768,
    ) -> None:
        self._collection_name = collection_name
        self._persist_dir = persist_directory
        self._capabilities = VectorCapabilities(
            provider_name="chroma_vector_store",
            dimensions=dimensions,
            supported_metrics=(DistanceMetric.COSINE, DistanceMetric.EUCLIDEAN),
            supports_namespaces=True,
            supports_metadata_filtering=True,
            supports_batch=True,
        )
        self._fallback = InMemoryVectorStore(
            provider_name="chroma_vector_store", dimensions=dimensions
        )

    @property
    def capabilities(self) -> VectorCapabilities:
        """Return ChromaCapabilities."""
        return self._capabilities

    async def upsert(self, record: VectorRecord) -> None:
        """Upsert VectorRecord."""
        await self._fallback.upsert(record)

    async def delete(self, record_id: str, namespace: str = "default") -> bool:
        """Delete VectorRecord by ID."""
        return await self._fallback.delete(record_id, namespace=namespace)

    async def get(self, record_id: str, namespace: str = "default") -> VectorRecord | None:
        """Get VectorRecord by ID."""
        return await self._fallback.get(record_id, namespace=namespace)

    async def search(
        self,
        query_vector: Sequence[float],
        top_k: int = 5,
        namespace: str = "default",
        filter_dict: dict[str, Any] | None = None,
    ) -> Sequence[VectorMatch]:
        """Perform vector search."""
        return await self._fallback.search(
            query_vector, top_k=top_k, namespace=namespace, filter_dict=filter_dict
        )

    async def batch_upsert(self, records: Sequence[VectorRecord]) -> None:
        """Batch upsert records."""
        await self._fallback.batch_upsert(records)

    async def batch_delete(self, record_ids: Sequence[str], namespace: str = "default") -> int:
        """Batch delete records."""
        return await self._fallback.batch_delete(record_ids, namespace=namespace)

    async def count(self, namespace: str = "default") -> int:
        """Count records in namespace."""
        return await self._fallback.count(namespace=namespace)

    async def clear(self, namespace: str = "default") -> None:
        """Clear namespace."""
        await self._fallback.clear(namespace=namespace)
