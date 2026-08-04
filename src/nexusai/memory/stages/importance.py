"""
ImportanceStage implementation for applying metadata importance weighting.
"""

from __future__ import annotations

from nexusai.memory.contracts.retrieval import RetrievalContext, RetrievalStage


class ImportanceStage(RetrievalStage):
    """RetrievalStage middleware attaching importance scores."""

    async def execute(self, context: RetrievalContext) -> None:
        """Populate sub_scores with metadata importance."""
        for record in context.candidate_records:
            importance = record.metadata.importance

            if record.id not in context.sub_scores:
                context.sub_scores[record.id] = {}
            context.sub_scores[record.id]["importance"] = importance
