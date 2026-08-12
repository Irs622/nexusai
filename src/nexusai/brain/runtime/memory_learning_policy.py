"""MemoryLearningPolicy implementing promotion decisions for episodic and semantic memory candidates."""

from __future__ import annotations

from nexusai.brain.domain.memory import MemoryType
from nexusai.brain.domain.memory_learning import (
    MemoryCandidate,
    MemoryPromotionDecision,
)
from nexusai.brain.ports.memory_learning_port import IMemoryLearningPolicy


class MemoryLearningPolicy(IMemoryLearningPolicy):
    """Policy engine deciding whether a candidate becomes episodic memory, semantic promotion, or is discarded."""

    def __init__(
        self,
        semantic_confidence_threshold: float = 0.85,
    ) -> None:
        self.semantic_confidence_threshold = semantic_confidence_threshold

    async def decide(
        self,
        candidate: MemoryCandidate,
    ) -> MemoryPromotionDecision:
        """Evaluate candidate memory and return explicit promotion decision."""
        if candidate.memory_type == MemoryType.WORKING:
            return MemoryPromotionDecision.DISCARD

        if candidate.memory_type == MemoryType.EPISODIC:
            return MemoryPromotionDecision.STORE_EPISODIC

        if candidate.memory_type == MemoryType.SEMANTIC:
            if candidate.confidence >= self.semantic_confidence_threshold:
                return MemoryPromotionDecision.PROMOTE_SEMANTIC
            return MemoryPromotionDecision.DISCARD

        return MemoryPromotionDecision.DISCARD
