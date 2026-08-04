"""
MemoryQueryService handling retrieval and search operations.
"""

from __future__ import annotations

from typing import Any

from nexusai.memory.contracts.retrieval import QueryResult
from nexusai.memory.domain.record import MemoryRecord
from nexusai.memory.metrics import MemoryMetricsCollector
from nexusai.memory.usecases.retrieve import RetrieveMemoryUseCase
from nexusai.memory.usecases.search import SearchMemoryUseCase


class MemoryQueryService:
    """Service handling read/search retrieval memory operations."""

    def __init__(
        self,
        retrieve_usecase: RetrieveMemoryUseCase,
        search_usecase: SearchMemoryUseCase,
        metrics: MemoryMetricsCollector | None = None,
    ) -> None:
        self._retrieve_usecase = retrieve_usecase
        self._search_usecase = search_usecase
        self._metrics = metrics or MemoryMetricsCollector()

    async def retrieve(self, record_id: str) -> MemoryRecord | None:
        """Retrieve MemoryRecord by ID."""
        return await self._retrieve_usecase.execute(record_id=record_id)

    async def search(
        self,
        query: str,
        top_k: int = 5,
        metadata_filters: dict[str, Any] | None = None,
    ) -> QueryResult:
        """Search memory records."""
        self._metrics.increment_counter("search_count")
        return await self._search_usecase.execute(
            query=query, top_k=top_k, metadata_filters=metadata_filters
        )
