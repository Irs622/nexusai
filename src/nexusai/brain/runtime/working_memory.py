"""Rich WorkingMemory value object and RetryPolicy contract for NexusAI Agent Runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexusai.brain.compaction.result import CompactionResult
from nexusai.brain.domain.agent import AgentGoal, FailureRecord, PlanStep, StepStatus
from nexusai.brain.domain.artifacts import Artifact
from nexusai.brain.domain.observation_lifecycle import ObservationMetadata
from nexusai.core.errors import DuplicateObservationError
from nexusai.domain.models import Observation


@dataclass(frozen=True)
class RetryPolicy:
    """Explicit retry policy contract governing step execution retries.

    Attributes:
        max_attempts: Maximum number of execution attempts per step.
        backoff_factor: Exponential backoff delay multiplier.
        retryable_errors: List of error pattern strings considered retryable.
    """

    max_attempts: int = 3
    backoff_factor: float = 2.0
    retryable_errors: list[str] = field(
        default_factory=lambda: ["TIMEOUT", "NETWORK_ERROR", "RATE_LIMIT", "TRANSIENT_FAILURE"]
    )

    def is_retryable(self, failure: FailureRecord, current_attempts: int) -> bool:
        """Evaluate whether a failure is retryable under policy rules."""
        if current_attempts >= self.max_attempts:
            return False
        if not self.retryable_errors:
            return True
        return any(err.lower() in failure.error_message.lower() for err in self.retryable_errors)


@dataclass
class WorkingMemory:
    """Ephemeral agent working memory tracking active goal state.

    Decoupled from persistent long-term conversation history and ExecutionContext telemetry.

    Attributes:
        goal: Target AgentGoal entity.
        steps: List of PlanStep step definitions.
        current_step_index: Single source of truth index for active step.
        scratchpad: Ephemeral reasoning logs and intermediate thought entries.
        context_variables: Strongly scoped data variables passed between steps.
        observations: Sequence of normalized Observation entities.
        temporary_artifacts: Artifacts generated during turn iterations.
        failures: Log of step execution failures.
        retry_count: Total retry attempts executed for active step.
        retry_policy: Active RetryPolicy rules.
    """

    goal: AgentGoal
    steps: list[PlanStep] = field(default_factory=list)
    current_step_index: int = 0
    scratchpad: list[str] = field(default_factory=list)
    context_variables: dict[str, Any] = field(default_factory=dict)
    observations: list[Observation] = field(default_factory=list)
    _metadata_by_id: dict[str, ObservationMetadata] = field(default_factory=dict)
    temporary_artifacts: list[Artifact] = field(default_factory=list)
    failures: list[FailureRecord] = field(default_factory=list)
    retry_count: int = 0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)

    def __post_init__(self) -> None:
        """Ensure 1-to-1 invariant between observations and metadata_by_id."""
        for obs in self.observations:
            if obs.id not in self._metadata_by_id:
                self._metadata_by_id[obs.id] = ObservationMetadata(observation_id=obs.id)

    @property
    def current_step(self) -> PlanStep | None:
        """Single source of truth property resolving current active PlanStep."""
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def advance_step(self) -> PlanStep | None:
        """Mark current step completed and advance current_step_index."""
        curr = self.current_step
        if curr is not None:
            curr.status = StepStatus.COMPLETED

        self.current_step_index += 1
        self.retry_count = 0
        nxt = self.current_step
        if nxt is not None:
            nxt.status = StepStatus.RUNNING
        return nxt

    def add_scratchpad_entry(self, entry: str) -> None:
        """Append an ephemeral thought or reasoning entry to scratchpad."""
        self.scratchpad.append(entry)

    def record_observation(
        self, observation: Observation, metadata: ObservationMetadata | None = None
    ) -> None:
        """Record a normalized tool or system observation and maintain metadata invariant."""
        if any(o.id == observation.id for o in self.observations):
            raise DuplicateObservationError(
                f"Duplicate observation ID '{observation.id}' rejected."
            )

        self.observations.append(observation)
        meta = metadata or ObservationMetadata(observation_id=observation.id)
        self._metadata_by_id[observation.id] = meta

    def remove_observation(self, observation_id: str) -> Observation | None:
        """Remove observation by ID and clean up metadata to prevent orphans."""
        target_obs: Observation | None = None
        for obs in list(self.observations):
            if obs.id == observation_id:
                target_obs = obs
                self.observations.remove(obs)
                break

        if observation_id in self._metadata_by_id:
            del self._metadata_by_id[observation_id]

        return target_obs

    def get_observation_metadata(self, observation_id: str) -> ObservationMetadata | None:
        """Retrieve ObservationMetadata by observation UUID string."""
        return self._metadata_by_id.get(observation_id)

    def has_observation_metadata(self, observation_id: str) -> bool:
        """Check if metadata exists for observation UUID string."""
        return observation_id in self._metadata_by_id

    def record_failure(self, step_id: int, error_message: str) -> FailureRecord:
        """Record a step execution failure record and increment retry count."""
        self.retry_count += 1
        failure = FailureRecord(
            step_id=step_id,
            error_message=error_message,
            retry_count=self.retry_count,
        )
        self.failures.append(failure)
        return failure

    def apply_compaction(self, result: CompactionResult) -> None:
        """Pure state assignment of CompactionResult delta. ZERO calculation logic."""
        # Mark compacted observations
        for obs in result.compacted_observations:
            if obs.id in self._metadata_by_id:
                self._metadata_by_id[obs.id].mark_compacted()

        # Clean up discarded metadata to prevent orphans
        for obs in result.discarded_observations:
            if obs.id in self._metadata_by_id:
                del self._metadata_by_id[obs.id]

        # Prune older compacted metadata to bound dictionary size during long sessions
        valid_ids = {o.id for o in result.retained_observations} | {
            o.id for o in result.compacted_observations
        }
        for obs_id in list(self._metadata_by_id.keys()):
            if obs_id not in valid_ids:
                del self._metadata_by_id[obs_id]

        self.observations = list(result.retained_observations)
        if result.summary_block:
            self.add_scratchpad_entry(str(result.summary_block))
            if len(self.scratchpad) > 50:
                self.scratchpad = self.scratchpad[-50:]
