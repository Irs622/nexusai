"""IMemoryExtractor, IMemoryLearningPolicy, and IMemoryLifecycle protocol contracts."""

from __future__ import annotations

from typing import Protocol, Sequence

from nexusai.brain.domain.agent_loop import Observation
from nexusai.brain.domain.memory_learning import (
    MemoryCandidate,
    MemoryExtractionResult,
    MemoryLearningResult,
    MemoryPromotionDecision,
)


class IMemoryExtractor(Protocol):
    """Abstract port identifying candidate learned memories from execution observations."""

    async def extract(
        self,
        *,
        session_id: str,
        execution_id: str,
        observations: Sequence[Observation],
        user_prompt: str,
    ) -> MemoryExtractionResult:
        """Identify candidate memory entries from execution results. MUST NOT persist directly."""
        ...


class IMemoryLearningPolicy(Protocol):
    """Abstract port evaluating candidate memory promotion decisions."""

    async def decide(
        self,
        candidate: MemoryCandidate,
    ) -> MemoryPromotionDecision:
        """Evaluate candidate memory and return explicit promotion decision. MUST NOT persist directly."""
        ...


class IMemoryLifecycle(Protocol):
    """Abstract port for context retrieval before planning and memory learning after execution."""

    async def retrieve_context(
        self,
        *,
        session_id: str,
        query_text: str,
    ) -> str:
        """Retrieve bounded context for planning input strictly enforcing session isolation."""
        ...

    async def learn_from_execution(
        self,
        *,
        session_id: str,
        execution_id: str,
        user_prompt: str,
        observations: Sequence[Observation],
    ) -> MemoryLearningResult:
        """Extract, evaluate, and persist episodic memory and qualified semantic memory candidates."""
        ...
