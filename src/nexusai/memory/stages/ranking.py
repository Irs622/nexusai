"""
RankingStage implementation for sorting candidate records by final score.
"""

from __future__ import annotations

from nexusai.memory.contracts.retrieval import RetrievalContext, RetrievalStage


class RankingStage(RetrievalStage):
    """RetrievalStage middleware sorting candidate records by calculated final scores."""

    async def execute(self, context: RetrievalContext) -> None:
        """Sort candidate_records in-place by score descending."""
        context.candidate_records.sort(
            key=lambda r: context.scores.get(r.id, 0.0),
            reverse=True,
        )
