"""
MockVectorStore implementation for deterministic testing.
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


class MockVectorStore(VectorStore):
    """MockVectorStore wrapper around InMemoryVectorStore for testing."""

    def __init__(self, provider_name: str = "mock_vector_store", dimensions: int = 768) -> None:
        self._inner = InMemoryVectorStore(provider_name=provider_name, dimensions=dimensions)

    @property
    def capabilities(self) -> VectorCapabilities:
        return self._inner.capabilities

    async def upsert(self, record: VectorRecord) -> None:
        await self._inner.upsert(record)

    async def delete(self, record_id: str, namespace: str = "default") -> bool:
        return await self._inner.delete(record_id, namespace=namespace)

    async def get(self, record_id: str, namespace: str = "default") -> VectorRecord | None:
        return await self._inner.get(record_id, namespace=namespace)

    async def search(
        self,
        query_vector: Sequence[float],
        top_k: int = 5,
        namespace: str = "default",
        filter_dict: dict[str, Any] | None = None,
    ) -> Sequence[VectorMatch]:
        return await self._inner.search(query_vector, top_k=top_k, namespace=namespace, filter_dict=filter_dict)

    async def batch_upsert(self, records: Sequence[VectorRecord]) -> None:
        await self._inner.batch_upsert(records)

    async def batch_delete(self, record_ids: Sequence[str], namespace: str = "default") -> int:
        return await self._inner.batch_delete(record_ids, namespace=namespace)

    async def count(self, namespace: str = "default") -> int:
        return await self._inner.count(namespace=namespace)

    async def clear(self, namespace: str = "default") -> None:
        await self._inner.clear(namespace=namespace)
