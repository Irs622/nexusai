"""RetentionPolicy and ImportancePolicy scoring abstractions for NexusAI Context Compaction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable

from nexusai.brain.domain.observation_lifecycle import ObservationMetadata
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.domain.models import Observation


@dataclass(frozen=True)
class RetentionPolicy:
    """Pure configuration container specifying WHAT memory items to retain.

    Contains ZERO calculation, decision logic, or Observation dependencies (pure value object).

    Attributes:
        max_active_observations: Maximum number of uncompacted active observations retained.
        max_failure_records: Maximum failure records retained in working context.
        preserve_artifacts: Boolean flag ensuring artifact-generating observations are protected.
        max_summary_units: ContextUnits ceiling for generated context summaries.
    """

    max_active_observations: int = 10
    max_failure_records: int = 5
    preserve_artifacts: bool = True
    max_summary_units: int = 500


@runtime_checkable
class ImportancePolicy(Protocol):
    """Protocol defining scoring rules for memory observation importance evaluation."""

    def evaluate(
        self,
        observation: Observation,
        metadata: ObservationMetadata,
        memory: WorkingMemory,
    ) -> float:
        """Calculate numerical importance score between 0.0 and 1.0."""
        ...


@dataclass(frozen=True)
class LinearPolicy:
    """Linear combination policy scoring observations based on immutable weighted feature components."""

    failure_weight: float = 0.35
    tool_state_change_weight: float = 0.25
    recency_weight: float = 0.25
    artifact_weight: float = 0.15

    def evaluate(
        self,
        observation: Observation,
        metadata: ObservationMetadata,
        memory: WorkingMemory,
    ) -> float:
        """Calculate weighted feature sum normalized between 0.0 and 1.0."""
        # 1. Failure Component
        failure_score = 1.0 if not observation.success or observation.severity == "ERROR" else 0.0

        # 2. Tool State-Change Component (Write/Modify actions)
        state_changing_keywords = {"write", "create", "delete", "update", "modify", "save", "post"}
        tool_name = (observation.tool_name or "").lower()
        tool_score = 1.0 if any(kw in tool_name for kw in state_changing_keywords) else 0.4

        # 3. Recency Component
        total_obs = len(memory.observations)
        if total_obs > 0:
            try:
                idx = memory.observations.index(observation)
                recency_score = (idx + 1) / total_obs
            except ValueError:
                recency_score = 0.5
        else:
            recency_score = 1.0

        # 4. Artifact Component
        artifact_score = 1.0 if observation.artifacts or metadata.is_important else 0.0

        score = (
            self.failure_weight * failure_score
            + self.tool_state_change_weight * tool_score
            + self.recency_weight * recency_score
            + self.artifact_weight * artifact_score
        )
        return min(1.0, max(0.0, score))


@dataclass(frozen=True)
class Rule:
    """Individual rule predicate mapping observation condition to importance score."""

    name: str
    predicate: Callable[[Observation, ObservationMetadata, WorkingMemory], bool]
    score: float


@dataclass(frozen=True)
class RulePolicy:
    """Rule collection policy evaluating ordered rules to assign importance scores."""

    rules: list[Rule] = field(
        default_factory=lambda: [
            Rule("explicit_important", lambda o, m, w: m.is_important, 1.0),
            Rule("failure_error", lambda o, m, w: not o.success or o.severity == "ERROR", 0.9),
            Rule("artifact_generated", lambda o, m, w: bool(o.artifacts), 0.8),
        ]
    )

    def evaluate(
        self,
        observation: Observation,
        metadata: ObservationMetadata,
        memory: WorkingMemory,
    ) -> float:
        """Evaluate rules in order, returning score of first matching rule or recency fallback."""
        for rule in self.rules:
            if rule.predicate(observation, metadata, memory):
                return rule.score

        # Fall back to recency-based priority
        total = len(memory.observations)
        if total > 0:
            try:
                idx = memory.observations.index(observation)
                return 0.2 + 0.5 * ((idx + 1) / total)
            except ValueError:
                return 0.3
        return 0.5


class ImportanceScorer:
    """Pure, stateless scorer calculating numerical importance scores using an injected ImportancePolicy."""

    def __init__(self, policy: ImportancePolicy | None = None) -> None:
        self.policy = policy or RulePolicy()

    def score_observation(
        self,
        observation: Observation,
        memory: WorkingMemory,
    ) -> float:
        """Pure stateless calculation returning numerical importance score for an Observation."""
        metadata = memory.get_observation_metadata(observation.id)
        if metadata is None:
            metadata = ObservationMetadata(observation_id=observation.id)

        return self.policy.evaluate(observation, metadata, memory)
