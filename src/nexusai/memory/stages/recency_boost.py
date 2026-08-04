"""
RecencyBoostStage implementation for time-decay score adjustments.
"""

from __future__ import annotations

import math
import time

from nexusai.memory.contracts.retrieval import RetrievalContext, RetrievalStage


class RecencyBoostStage(RetrievalStage):
    """RetrievalStage middleware boosting scores for recently created/updated records."""

    def __init__(self, decay_half_life_hours: float = 24.0) -> None:
        self._decay_lambda = math.log(2) / (decay_half_life_hours * 3600.0)

    async def execute(self, context: RetrievalContext) -> None:
        """Calculate recency score and populate sub_scores."""
        now = time.time()
        for record in context.candidate_records:
            age_seconds = max(0.0, now - record.metadata.updated_at)
            recency_score = math.exp(-self._decay_lambda * age_seconds)

            if record.id not in context.sub_scores:
                context.sub_scores[record.id] = {}
            context.sub_scores[record.id]["recency"] = recency_score
