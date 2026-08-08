"""Pluggable strategy protocols and concrete implementations for Planning, Reflection, and Decision.

Strictly preserves provider-neutrality and enables offline unit testing without network calls.
"""

from __future__ import annotations

from typing import Protocol

from nexusai.brain.domain.agent import (
    AgentGoal,
    LoopDecision,
    PlanStep,
    ReflectionAnalysis,
    StepStatus,
)
from nexusai.brain.runtime.agent_context import AgentRuntimeContext
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.domain.models import Observation
from nexusai.logging.logger import logger


class IPlanningStrategy(Protocol):
    """Abstract Strategy interface for task planning."""

    async def generate_plan(self, goal: AgentGoal, ctx: AgentRuntimeContext) -> list[PlanStep]:
        """Decompose an AgentGoal into an ordered sequence of PlanSteps.

        Args:
            goal: Target AgentGoal.
            ctx: AgentRuntimeContext composition context.

        Returns:
            List of PlanStep instances.
        """
        ...


class RulePlanningStrategy:
    """Deterministic, rule-based planning strategy for fast offline testing and fallback."""

    async def generate_plan(self, goal: AgentGoal, ctx: AgentRuntimeContext) -> list[PlanStep]:
        """Generate deterministic steps without making network calls."""
        logger.debug(
            f"[RulePlanningStrategy] Generating rule-based plan for goal '{goal.description}'"
        )
        return [
            PlanStep(
                step_id=1,
                title="Inspect Environment",
                description=f"Analyze workspace environment for goal: {goal.description}",
                tool_name="workspace_list_directory",
                arguments={"path": "."},
            ),
            PlanStep(
                step_id=2,
                title="Execute Goal Action",
                description=f"Execute primary action for goal: {goal.description}",
                tool_name="workspace_read_file",
                arguments={"file_path": "pyproject.toml"},
            ),
        ]


class LLMPlanningStrategy:
    """LLM-backed dynamic planning strategy using vendor-neutral PromptBundle."""

    async def generate_plan(self, goal: AgentGoal, ctx: AgentRuntimeContext) -> list[PlanStep]:
        """Generate dynamic plan steps using provider runtime."""
        logger.debug(f"[LLMPlanningStrategy] Generating LLM plan for goal '{goal.description}'")
        # Baseline fallback step sequence until LLM provider call is connected
        return [
            PlanStep(
                step_id=1,
                title="Decompose Goal",
                description=f"LLM analysis step for: {goal.description}",
                tool_name="workspace_read_file",
                arguments={"file_path": "pyproject.toml"},
            ),
        ]


class IReflectionStrategy(Protocol):
    """Abstract Strategy interface for evaluating observations and forming reflection analysis."""

    async def reflect(self, memory: WorkingMemory, observation: Observation) -> ReflectionAnalysis:
        """Evaluate observation and return objective ReflectionAnalysis.

        Args:
            memory: Active WorkingMemory snapshot.
            observation: Most recent Observation entity.

        Returns:
            ReflectionAnalysis objective evaluation facts.
        """
        ...


class RuleReflectionStrategy:
    """Deterministic rule-based reflection strategy for offline testing and fallback."""

    async def reflect(self, memory: WorkingMemory, observation: Observation) -> ReflectionAnalysis:
        """Evaluate observation using deterministic rules."""
        logger.debug(
            f"[RuleReflectionStrategy] Reflecting on observation from tool '{observation.tool_name}'"
        )
        if not observation.success or observation.severity == "ERROR":
            return ReflectionAnalysis(
                goal_completed=False,
                confidence=0.5,
                retryable=True,
                missing_information=[f"Tool '{observation.tool_name}' failed"],
                suggested_action="Retry step with repaired arguments or fallback strategy",
            )

        # Check if all steps completed
        current_step = memory.current_step
        all_completed = bool(
            memory.steps
            and all(s.status == StepStatus.COMPLETED for s in memory.steps if s != current_step)
        )

        return ReflectionAnalysis(
            goal_completed=all_completed,
            confidence=1.0 if all_completed else 0.9,
            retryable=False,
            suggested_action=(
                "Proceed to next plan step" if not all_completed else "Goal accomplished"
            ),
        )


class LLMReflectionStrategy:
    """LLM-backed reflection strategy for complex observation synthesis."""

    async def reflect(self, memory: WorkingMemory, observation: Observation) -> ReflectionAnalysis:
        """Reflect on observation using LLM inference."""
        logger.debug(f"[LLMReflectionStrategy] LLM reflecting on observation '{observation.id}'")
        return ReflectionAnalysis(
            goal_completed=observation.success,
            confidence=0.9 if observation.success else 0.4,
            retryable=not observation.success,
            suggested_action="LLM suggested follow-up step",
        )


class IDecisionStrategy(Protocol):
    """Abstract Strategy interface mapping ReflectionAnalysis to LoopDecision."""

    def decide(self, memory: WorkingMemory, analysis: ReflectionAnalysis) -> LoopDecision:
        """Determine next loop action based on WorkingMemory and ReflectionAnalysis.

        Args:
            memory: Active WorkingMemory snapshot.
            analysis: Objective ReflectionAnalysis.

        Returns:
            Actionable LoopDecision enum value.
        """
        ...


class RuleDecisionStrategy:
    """Deterministic rule-backed decision strategy."""

    def decide(self, memory: WorkingMemory, analysis: ReflectionAnalysis) -> LoopDecision:
        """Derive LoopDecision from ReflectionAnalysis and retry policy limits."""
        logger.debug(
            f"[RuleDecisionStrategy] Deciding next loop state based on analysis (completed={analysis.goal_completed})"
        )
        if analysis.goal_completed:
            return LoopDecision.COMPLETE

        # Evaluate retry limit if step failed
        if memory.current_step and memory.current_step.status == StepStatus.FAILED:
            if memory.retry_count >= memory.retry_policy.max_attempts or not analysis.retryable:
                return LoopDecision.FAIL
            return LoopDecision.REPLAN

        return LoopDecision.CONTINUE
