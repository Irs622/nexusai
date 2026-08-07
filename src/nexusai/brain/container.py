"""RuntimeDependencies typed container for NexusAI Agent Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from nexusai.brain.compaction.budget import CharacterEstimator, ContextBudget, IContextEstimator
from nexusai.brain.compaction.importance import RetentionPolicy
from nexusai.brain.compaction.pipeline import CompactionPipeline
from nexusai.brain.failure_detector import FailureClassifier
from nexusai.brain.strategy import (
    IDecisionStrategy,
    IPlanningStrategy,
    IReflectionStrategy,
    RuleDecisionStrategy,
    RulePlanningStrategy,
    RuleReflectionStrategy,
)


@dataclass(frozen=True)
class RuntimeDependencies:
    """Strongly-typed dependency injection container for LoopExecutor and AgentRuntime.

    Prevents God Service and Service Locator anti-patterns via explicit attribute fields.
    """

    planning_strategy: IPlanningStrategy = RulePlanningStrategy()
    reflection_strategy: IReflectionStrategy = RuleReflectionStrategy()
    decision_strategy: IDecisionStrategy = RuleDecisionStrategy()
    compaction_pipeline: CompactionPipeline = CompactionPipeline()
    failure_classifier: FailureClassifier = FailureClassifier()
    retention_policy: RetentionPolicy = RetentionPolicy()
    context_budget: ContextBudget = ContextBudget()
    context_estimator: IContextEstimator = CharacterEstimator()
