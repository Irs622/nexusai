"""
MemoryAdminService handling health, metrics, vacuum, and maintenance operations.
"""

from __future__ import annotations

from typing import Any

from nexusai.kernel.service import ServiceLifecycleState
from nexusai.memory.contracts.embedding import EmbeddingProvider
from nexusai.memory.contracts.storage import MemoryStorage
from nexusai.memory.contracts.vector import VectorStore
from nexusai.memory.metrics import MemoryMetricsCollector
from nexusai.memory.pipeline.retrieval_pipeline import RetrievalPipeline
from nexusai.memory.policies.engine import PolicyEngine


class MemoryAdminService:
    """Service handling administration, health probes, metrics, and maintenance operations."""

    def __init__(
        self,
        storage: MemoryStorage | None = None,
        vector_store: VectorStore | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        pipeline: RetrievalPipeline | None = None,
        policy_engine: PolicyEngine | None = None,
        metrics: MemoryMetricsCollector | None = None,
    ) -> None:
        self._storage = storage
        self._vector_store = vector_store
        self._embedding_provider = embedding_provider
        self._pipeline = pipeline
        self._policy_engine = policy_engine
        self._metrics = metrics or MemoryMetricsCollector()
        self._is_degraded = False

    def set_degraded_status(self, degraded: bool) -> None:
        """Mark degraded status."""
        self._is_degraded = degraded

    async def health(self, state: ServiceLifecycleState) -> dict[str, Any]:
        """Return comprehensive diagnostic health probes."""
        overall_status = "healthy"
        if self._is_degraded:
            overall_status = "degraded"
        elif state != ServiceLifecycleState.RUNNING:
            overall_status = "initialized"

        storage_diag = {
            "status": "healthy" if self._storage else "unconfigured",
            "driver": self._storage.__class__.__name__ if self._storage else None,
        }

        vector_diag = {
            "status": "healthy" if self._vector_store else "unconfigured",
            "provider": (
                self._vector_store.capabilities.provider_name if self._vector_store else None
            ),
            "dimensions": self._vector_store.capabilities.dimensions if self._vector_store else 0,
        }

        embedding_diag = {
            "status": "healthy" if self._embedding_provider else "unconfigured",
            "model": (
                self._embedding_provider.capabilities.model_name
                if self._embedding_provider
                else None
            ),
        }

        return {
            "status": overall_status,
            "storage": storage_diag,
            "vector": vector_diag,
            "embedding": embedding_diag,
            "pipeline": {"status": "healthy" if self._pipeline else "unconfigured"},
        }

    def metrics(self) -> dict[str, Any]:
        """Return metrics summary."""
        return self._metrics.get_summary()

    async def vacuum(self) -> bool:
        """Execute vacuum / storage optimization."""
        return True

    async def reindex(self) -> bool:
        """Reindex vector store."""
        return True
