"""
SimilarityStage implementation for attaching vector similarity search scores.
"""

from __future__ import annotations

from nexusai.memory.contracts.retrieval import RetrievalContext, RetrievalStage
from nexusai.memory.contracts.vector import VectorStore


class SimilarityStage(RetrievalStage):
    """RetrievalStage middleware attaching similarity scores from VectorStore."""

    def __init__(self, vector_store: VectorStore) -> None:
        self._vector_store = vector_store

    async def execute(self, context: RetrievalContext) -> None:
        """Execute vector similarity search and assign sub_scores."""
        if not context.embedding:
            return

        matches = await self._vector_store.search(
            query_vector=context.embedding,
            top_k=len(context.candidate_records) or 10,
            filter_dict=context.metadata_filters or None,
        )

        match_map = {m.record_id: m.similarity for m in matches}
        for record in context.candidate_records:
            sim_score = match_map.get(record.id, 0.5)
            if record.id not in context.sub_scores:
                context.sub_scores[record.id] = {}
            context.sub_scores[record.id]["similarity"] = sim_score
            context.scores[record.id] = sim_score
