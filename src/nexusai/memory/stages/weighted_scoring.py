"""
WeightedScoringStage for generic feature vector dot product scoring.
"""

from __future__ import annotations

from typing import Any

from nexusai.memory.contracts.retrieval import RetrievalContext, RetrievalStage


class WeightedScoringStage(RetrievalStage):
    """RetrievalStage middleware evaluating generic feature vector dot products."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._weights = weights or {
            "similarity": 0.7,
            "recency": 0.2,
            "importance": 0.1,
        }

    async def execute(self, context: RetrievalContext) -> None:
        """Calculate score = sum(feature * weight) over all attached sub_scores features."""
        # Dynamic weights override from context
        override_weights = context.trace_context.get("pipeline_weights")
        if isinstance(override_weights, dict):
            self._weights.update(override_weights)

        for record in context.candidate_records:
            features = context.sub_scores.get(record.id, {})

            # Dot product over all present features
            score = 0.0
            total_weight = 0.0

            for feat_key, feat_val in features.items():
                w = self._weights.get(feat_key, 0.0)
                score += feat_val * w
                total_weight += w

            # Normalize if weights present
            if total_weight > 0.0:
                score = score / total_weight

            context.scores[record.id] = score
