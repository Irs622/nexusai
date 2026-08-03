"""Pluggable ReasoningEngine Host for NexusAI."""
from typing import Optional
from nexusai.domain.models import Goal, GoalPlan, Observation, EvaluationResult, GoalCompletionStatus
from nexusai.brain.inference import InferenceService
from nexusai.brain.strategy import PlanningStrategy, HeuristicPlanningStrategy, RepairStrategy, DefaultRepairStrategy

class ReasoningEngine:
    """Pluggable Reasoning Engine holding Planning, Tool Selection, Repair, and Reflection Strategies."""

    def __init__(
        self,
        inference: Optional[InferenceService] = None,
        planning_strategy: Optional[PlanningStrategy] = None,
        repair_strategy: Optional[RepairStrategy] = None,
    ) -> None:
        self.inference = inference or InferenceService()
        self.planning_strategy = planning_strategy or HeuristicPlanningStrategy()
        self.repair_strategy = repair_strategy or DefaultRepairStrategy()

    async def generate_plan(self, goal: Goal) -> GoalPlan:
        """Delegate goal planning to configured planning strategy."""
        return await self.planning_strategy.plan_goal(goal, self.inference)

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
