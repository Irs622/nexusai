"""
InMemoryVectorStore implementation supporting cosine similarity, namespaces, and metadata filtering.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from nexusai.memory.contracts.vector import (
    DistanceMetric,
    VectorCapabilities,
    VectorMatch,
    VectorRecord,
    VectorStore,
)


def cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
    """Calculate cosine similarity float value between two vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


class InMemoryVectorStore(VectorStore):
    """In-memory vector store engine using cosine similarity."""

    def __init__(self, provider_name: str = "in_memory_vector", dimensions: int = 768) -> None:
        self._capabilities = VectorCapabilities(
            provider_name=provider_name,
            dimensions=dimensions,
            supported_metrics=(DistanceMetric.COSINE,),
            supports_namespaces=True,
            supports_metadata_filtering=True,
            supports_batch=True,
        )
        self._namespaces: dict[str, dict[str, VectorRecord]] = {}

    @property
    def capabilities(self) -> VectorCapabilities:
        """Return vector store capabilities."""
        return self._capabilities

    def _get_ns(self, namespace: str) -> dict[str, VectorRecord]:
        if namespace not in self._namespaces:
            self._namespaces[namespace] = {}
        return self._namespaces[namespace]

    async def upsert(self, record: VectorRecord) -> None:
        """Upsert single VectorRecord."""
        ns = self._get_ns(record.namespace)
        ns[record.record_id] = record

    async def delete(self, record_id: str, namespace: str = "default") -> bool:
        """Delete single vector record by ID."""
        ns = self._get_ns(namespace)
        if record_id in ns:
            del ns[record_id]
            return True
        return False

    async def get(self, record_id: str, namespace: str = "default") -> VectorRecord | None:
        """Get vector record by ID."""
        ns = self._get_ns(namespace)
        return ns.get(record_id)

    async def search(
        self,
        query_vector: Sequence[float],
        top_k: int = 5,
        namespace: str = "default",
        filter_dict: dict[str, Any] | None = None,
    ) -> Sequence[VectorMatch]:
        """Perform cosine similarity search with metadata filtering."""
        ns = self._get_ns(namespace)
        matches: list[VectorMatch] = []

        for r in ns.values():
            # Apply metadata filter
            if filter_dict:
                match_filter = all(r.metadata.get(k) == v for k, v in filter_dict.items())
                if not match_filter:
                    continue

            sim = cosine_similarity(query_vector, r.vector)
            dist = 1.0 - sim
            matches.append(
                VectorMatch(
                    record_id=r.record_id,
                    distance=dist,
                    similarity=sim,
                    metadata=r.metadata,
                    payload=r.payload,
                    namespace=namespace,
                )
            )

        matches.sort(key=lambda m: m.similarity, reverse=True)
        return matches[:top_k]

    async def batch_upsert(self, records: Sequence[VectorRecord]) -> None:
        """Upsert batch of records."""
        for r in records:
            await self.upsert(r)

    async def batch_delete(self, record_ids: Sequence[str], namespace: str = "default") -> int:
        """Delete batch of records returning count deleted."""
        cnt = 0
        for rid in record_ids:
            if await self.delete(rid, namespace=namespace):
                cnt += 1
        return cnt

    async def count(self, namespace: str = "default") -> int:
        """Count total vector records in namespace."""
        ns = self._get_ns(namespace)
        return len(ns)

    async def clear(self, namespace: str = "default") -> None:
        """Clear namespace."""
        if namespace in self._namespaces:
            self._namespaces[namespace].clear()
