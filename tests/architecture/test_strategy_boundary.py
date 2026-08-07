"""Architecture Fitness Test — Strategy Boundary & Builder Contract Invariants.

Verifies that strategies follow Protocol contracts and AgentRuntimeBuilder enforces runtime invariants upon .build().
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from nexusai.brain.builder import AgentRuntimeBuilder
from nexusai.brain.domain.agent import AgentGoal, PlanStep
from nexusai.brain.runtime.agent_context import AgentRuntimeContext
from nexusai.brain.strategy import (
    IDecisionStrategy,
    IPlanningStrategy,
    IReflectionStrategy,
    RuleDecisionStrategy,
    RulePlanningStrategy,
    RuleReflectionStrategy,
)


@runtime_checkable
class PlanningStrategyProtocol(Protocol):
    async def generate_plan(self, goal: AgentGoal, ctx: AgentRuntimeContext) -> list[PlanStep]:
        ...


def test_strategy_protocols():
    """Verify Rule strategies implement Protocol interfaces."""
    planner = RulePlanningStrategy()
    reflector = RuleReflectionStrategy()
    decider = RuleDecisionStrategy()

    assert isinstance(planner, PlanningStrategyProtocol)
    assert hasattr(reflector, "reflect")
    assert hasattr(decider, "decide")


def test_builder_dependency_injection():
    """Verify AgentRuntimeBuilder injects strategies dynamically into LoopExecutor."""
    builder = AgentRuntimeBuilder()
    builder.with_planning_strategy(RulePlanningStrategy())
    builder.with_reflection_strategy(RuleReflectionStrategy())
    builder.with_decision_strategy(RuleDecisionStrategy())

    executor = builder.build_executor()
    assert executor._planner.__class__.__name__ == "RulePlanningStrategy"
    assert executor._reflector.__class__.__name__ == "RuleReflectionStrategy"
    assert executor._decider.__class__.__name__ == "RuleDecisionStrategy"


def test_builder_post_build_invariants():
    """Verify AgentRuntimeBuilder enforces post-build invariants on AgentRuntimeFacade."""
    facade = (
        AgentRuntimeBuilder()
        .with_planning_strategy(RulePlanningStrategy())
        .with_reflection_strategy(RuleReflectionStrategy())
        .with_decision_strategy(RuleDecisionStrategy())
        .build()
    )

    assert facade._executor is not None, "LoopExecutor must be initialized!"
    assert facade._executor._planner is not None, "Planning strategy invariant failed!"
    assert facade._executor._reflector is not None, "Reflection strategy invariant failed!"
    assert facade._executor._decider is not None, "Decision strategy invariant failed!"
    assert facade._executor._obs_mapper is not None, "ObservationMapper invariant failed!"
    assert facade._executor._pipeline is not None, "ExecutionPipeline invariant failed!"


if __name__ == "__main__":
    test_strategy_protocols()
    test_builder_dependency_injection()
    test_builder_post_build_invariants()
    print("ALL STRATEGY BOUNDARY FITNESS TESTS PASSED SUCCESSFULLY!")
