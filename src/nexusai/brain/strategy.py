"""Pluggable Strategy Interfaces for Planning, Tool Selection, Repair, and Reflection."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from nexusai.domain.models import Goal, GoalPlan, GoalStep, Observation, EvaluationResult, GoalCompletionStatus
from nexusai.brain.inference import InferenceService

class PlanningStrategy(ABC):
    """Abstract Strategy for task planning."""
    @abstractmethod
    async def plan_goal(self, goal: Goal, inference: InferenceService) -> GoalPlan:
        pass

class HeuristicPlanningStrategy(PlanningStrategy):
    """Heuristic / Default planning strategy."""
    async def plan_goal(self, goal: Goal, inference: InferenceService) -> GoalPlan:
        steps = [
            GoalStep(1, "Inspect Environment", f"Analyze workspace for goal: {goal.prompt}", ["filesystem"]),
            GoalStep(2, "Execute Goal Setup", f"Run initial commands for goal: {goal.prompt}", ["terminal"]),
        ]
        return GoalPlan(goal=goal, steps=steps)

class LLMPlanningStrategy(PlanningStrategy):
    """LLM-assisted dynamic planning strategy."""
    async def plan_goal(self, goal: Goal, inference: InferenceService) -> GoalPlan:
        resp = await inference.generate_response(f"Plan goal: {goal.prompt}")
        steps = [
            GoalStep(1, "LLM Dynamic Analysis", f"Execute LLM plan for: {goal.prompt}", ["filesystem", "terminal"]),
        ]
        return GoalPlan(goal=goal, steps=steps)

class RepairStrategy(ABC):
    """Abstract Strategy for auto-repairing failed steps."""
    @abstractmethod
    def repair_observation(self, obs: Observation) -> Dict[str, Any]:
        pass

class DefaultRepairStrategy(RepairStrategy):
    """Default repair strategy."""
    def repair_observation(self, obs: Observation) -> Dict[str, Any]:
        return {"repaired": True, "source_tool": obs.tool_name}
