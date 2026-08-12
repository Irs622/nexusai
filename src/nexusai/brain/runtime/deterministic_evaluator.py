"""Deterministic outcome evaluator evaluating execution observations without unconstrained LLM ambiguity."""

from __future__ import annotations

from nexusai.brain.domain.agent_loop import AgentLoopConfig, LoopDecision, Observation
from nexusai.brain.domain.agent_runtime import AgentRequest
from nexusai.brain.ports.outcome_evaluator_port import IOutcomeEvaluator


class DeterministicOutcomeEvaluator(IOutcomeEvaluator):
    """Deterministic implementation evaluating node metrics, replan budgets, and progress signals."""

    async def evaluate(
        self,
        request: AgentRequest,
        observation: Observation,
        loop_config: AgentLoopConfig,
        iteration: int,
        replan_count: int,
    ) -> LoopDecision:
        """Evaluate observation metrics and return explicit LoopDecision."""
        if observation.failed_nodes > 0:
            if loop_config.allow_replanning and replan_count < loop_config.max_replans:
                return LoopDecision(
                    action="REPLAN",
                    reason=f"{observation.failed_nodes} node(s) failed; replanning permitted ({replan_count}/{loop_config.max_replans})",
                )
            else:
                return LoopDecision(
                    action="FAILED",
                    reason=f"{observation.failed_nodes} node(s) failed and replanning budget ({loop_config.max_replans}) is exhausted",
                )

        if observation.successful_nodes > 0 and observation.pending_nodes == 0:
            return LoopDecision(
                action="COMPLETED",
                reason=f"All {observation.successful_nodes} plan node(s) completed successfully",
            )

        return LoopDecision(
            action="COMPLETED",
            reason="Execution finished with zero failing nodes",
        )
