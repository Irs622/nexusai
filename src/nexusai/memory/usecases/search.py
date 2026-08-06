"""
SearchMemoryUseCase implementation.
"""

from __future__ import annotations

from typing import Any

from nexusai.memory.contracts.embedding import EmbeddingProvider
from nexusai.memory.contracts.retrieval import QueryResult, RetrievalContext
from nexusai.memory.pipeline.retrieval_pipeline import RetrievalPipeline
from nexusai.memory.uow.unit_of_work import MemoryUnitOfWork


class SearchMemoryUseCase:
    """Use case for searching memories via embedding and retrieval pipeline."""

    def __init__(
        self,
        uow: MemoryUnitOfWork,
        pipeline: RetrievalPipeline,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._uow = uow
        self._pipeline = pipeline
        self._embedding_provider = embedding_provider

    async def execute(
        self,
        query: str,
        top_k: int = 5,
        metadata_filters: dict[str, Any] | None = None,
    ) -> QueryResult:
        """Execute search usecase."""
        embedding = await self._embedding_provider.embed_text(query)
        candidates = await self._uow.records.list_all(limit=100)

        context = RetrievalContext(
            query=query,
            embedding=embedding,
            candidate_records=list(candidates),
            metadata_filters=metadata_filters,
        )

        return await self._pipeline.execute(context)
