"""IOutcomeEvaluator protocol contract decoupling outcome evaluation from agent loop control."""

from __future__ import annotations

from typing import Protocol

from nexusai.brain.domain.agent_loop import AgentLoopConfig, LoopDecision, Observation
from nexusai.brain.domain.agent_runtime import AgentRequest


class IOutcomeEvaluator(Protocol):
    """Abstract port interface evaluating execution observation outputs deterministically."""

    async def evaluate(
        self,
        request: AgentRequest,
        observation: Observation,
        loop_config: AgentLoopConfig,
        iteration: int,
        replan_count: int,
    ) -> LoopDecision:
        """Evaluate observation metrics and return explicit LoopDecision."""
        ...
