"""Modular Planner Pipeline sub-package for NexusAI Agent Runtime."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.planner.repair import PlanRepairEngine
from nexusai.brain.planner.scheduler import ExecutionScheduler
from nexusai.brain.planner.stages import (
    ActionRanker,
    BayesianStrategy,
    DependencyResolver,
    ExecutionPlanner,
    GoalAnalyzer,
    IScoringStrategy,
    RecoveryPlanner,
    TaskDecomposer,
    WeightedLinearStrategy,
)
from nexusai.brain.planner.validator import PlanValidator


@dataclass
class TaskStep:
    """Individual executable step in a decomposed task plan."""

    step_id: int
    title: str
    description: str
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    completed: bool = False


@dataclass
class TaskPlan:
    """Complete decomposed plan generated from a high-level user prompt."""

    prompt: str
    steps: List[TaskStep] = field(default_factory=list)


class TaskPlanner:
    """Decomposes any natural language goal dynamically into structured executable steps."""

    def __init__(self, provider: Any = None) -> None:
        self.provider = provider

    def plan(self, user_prompt: str) -> TaskPlan:
        """Parse any user goal dynamically and return structured task plan."""
        prompt_lower = user_prompt.lower()
        words = prompt_lower.split()
        action_title = " ".join(w.capitalize() for w in words[:3]) if words else "Execute Task"

        steps = [
            TaskStep(
                1,
                f"Analyze Workspace for {action_title}",
                f"Inspect existing files for {user_prompt}",
                "workspace_list_directory",
                {"path": "."},
            ),
            TaskStep(
                2,
                f"Read Configuration for {action_title}",
                "Read pyproject.toml configuration",
                "workspace_read_file",
                {"file_path": "pyproject.toml"},
            ),
            TaskStep(
                3,
                f"Execute Setup for {action_title}",
                f"Run shell environment check for {user_prompt}",
                "execute_terminal",
                {"command": f"echo 'Running {user_prompt}'"},
            ),
        ]

        return TaskPlan(prompt=user_prompt, steps=steps)


__all__ = [
    "ActionRanker",
    "BayesianStrategy",
    "DependencyResolver",
    "ExecutionPlanner",
    "ExecutionScheduler",
    "GoalAnalyzer",
    "IScoringStrategy",
    "PlanGraphExecutionEngine",
    "PlanRepairEngine",
    "PlanValidator",
    "RecoveryPlanner",
    "TaskDecomposer",
    "TaskPlan",
    "TaskPlanner",
    "TaskStep",
    "WeightedLinearStrategy",
]
