"""RuntimeDependencies typed container for NexusAI Agent Runtime."""

from __future__ import annotations

from dataclasses import dataclass, field

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
from nexusai.brain.telemetry.metrics import IMetricsCollector, InMemoryMetricsCollector


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
    metrics_collector: IMetricsCollector = field(default_factory=InMemoryMetricsCollector)

    def __post_init__(self) -> None:
        """Inject metrics_collector into compaction_pipeline if not present."""
        if self.compaction_pipeline and self.compaction_pipeline.metrics_collector is None:
            object.__setattr__(
                self,
                "compaction_pipeline",
                CompactionPipeline(
                    estimator=self.compaction_pipeline.estimator,
                    scorer=self.compaction_pipeline.scorer,
                    summary_generator=self.compaction_pipeline.summary_generator,
                    metrics_collector=self.metrics_collector,
                ),
            )
