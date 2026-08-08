"""Pluggable ReasoningEngine Host for NexusAI."""

from __future__ import annotations

from typing import Any, Optional, cast

from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.strategy import IPlanningStrategy, RulePlanningStrategy
from nexusai.domain.models import (
    EvaluationResult,
    Goal,
    GoalCompletionStatus,
    GoalPlan,
    Observation,
)


class ReasoningEngine:
    """Pluggable Reasoning Engine holding Planning, Tool Selection, Repair, and Reflection Strategies."""

    def __init__(
        self,
        inference: Any = None,
        planning_strategy: Optional[IPlanningStrategy] = None,
        repair_strategy: Any = None,
    ) -> None:
        self.inference = inference
        self.planning_strategy = planning_strategy or RulePlanningStrategy()
        self.repair_strategy = repair_strategy

    async def generate_plan(self, goal: Goal) -> GoalPlan:
        """Delegate goal planning to configured planning strategy."""
        agent_goal = AgentGoal(description=goal.prompt if hasattr(goal, "prompt") else str(goal))
        res = await self.planning_strategy.generate_plan(agent_goal, self.inference)
        return cast(GoalPlan, res)

    def evaluate_observation(self, obs: Observation) -> EvaluationResult:
        """Evaluate observation and return structured EvaluationResult."""
        if not obs.success or obs.severity == "ERROR":
            return EvaluationResult(
                goal_status=GoalCompletionStatus.PARTIAL,
                confidence=0.5,
                failure_reason=f"Tool '{obs.tool_name}' emitted error: {obs.payload}",
                repair_strategy="Retry with repaired parameters",
                retry_recommended=True,
            )

        return EvaluationResult(
            goal_status=GoalCompletionStatus.YES,
            confidence=1.0,
            failure_reason=None,
            repair_strategy=None,
            retry_recommended=False,
        )
