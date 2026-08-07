"""CompactionPipeline orchestrator driving context compaction and generating CompactionResult deltas."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from nexusai.brain.compaction.budget import CharacterEstimator, ContextBudget, IContextEstimator
from nexusai.brain.compaction.importance import ImportancePolicy, ImportanceScorer, RetentionPolicy
from nexusai.brain.compaction.result import CompactionResult, SummaryBlock
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.domain.models import Observation


@runtime_checkable
class ISummaryGenerator(Protocol):
    """Protocol interface for generating domain SummaryBlock objects from compacted observations."""

    def generate_summary(self, compacted_observations: list[Observation]) -> SummaryBlock:
        """Generate structured SummaryBlock value object."""
        ...


class StructuredSummaryGenerator:
    """Default deterministic summary generator formatting compacted observations into a SummaryBlock."""

    def generate_summary(self, compacted_observations: list[Observation]) -> SummaryBlock:
        """Format compacted observations into a structured SummaryBlock value object."""
        if not compacted_observations:
            return SummaryBlock(title="Context Summary", text="", observation_ids=())

        summary_lines = [f"[Context Summary: {len(compacted_observations)} observations compacted]"]
        obs_ids: list[str] = []
        for obs in compacted_observations:
            obs_ids.append(obs.id)
            tool_info = f"Tool '{obs.tool_name}'" if obs.tool_name else "Observation"
            status_info = "SUCCESS" if obs.success else "FAILED"
            payload_snippet = str(obs.payload)[:100].replace("\n", " ")
            summary_lines.append(f"- {tool_info} ({status_info}): {payload_snippet}")

        return SummaryBlock(
            title=f"Context Summary ({len(compacted_observations)} items)",
            text="\n".join(summary_lines),
            observation_ids=tuple(obs_ids),
        )


class CompactionPipeline:
    """Single-responsibility orchestrator running context compaction logic and returning CompactionResult.

    Does NOT mutate WorkingMemory directly (mutation occurs via WorkingMemory.apply_compaction).
    Organized into modular stage helper methods preparing for Phase 4 Staged Pipeline evolution.
    """

    def __init__(
        self,
        estimator: IContextEstimator | None = None,
        scorer: ImportanceScorer | None = None,
        summary_generator: ISummaryGenerator | None = None,
    ) -> None:
        self.estimator = estimator or CharacterEstimator()
        self.scorer = scorer or ImportanceScorer()
        self.summary_generator = summary_generator or StructuredSummaryGenerator()

    def _estimate(self, memory: WorkingMemory) -> int:
        """Helper Step 1: Estimate active ContextUnits in WorkingMemory."""
        return self.estimator.estimate_memory(memory)

    def _should_compact(self, current_units: int, memory: WorkingMemory, budget: ContextBudget, policy: RetentionPolicy) -> bool:
        """Helper Step 2: Evaluate warning threshold trigger condition."""
        if current_units <= budget.warning_units or len(memory.observations) <= policy.max_active_observations:
            return False
        return True

    def _score_observations(self, memory: WorkingMemory) -> list[tuple[Observation, float]]:
        """Helper Step 3 & 4: Score active observations statelessly and sort descending."""
        scored_obs: list[tuple[Observation, float]] = []
        for obs in memory.observations:
            score = self.scorer.score_observation(obs, memory)
            scored_obs.append((obs, score))

        scored_obs.sort(key=lambda item: item[1], reverse=True)
        return scored_obs

    def _partition_observations(
        self,
        scored_obs: list[tuple[Observation, float]],
        memory: WorkingMemory,
        policy: RetentionPolicy,
    ) -> tuple[list[Observation], list[Observation]]:
        """Helper Step 5: Partition observations into retained vs compacted sets."""
        retained: list[Observation] = []
        compacted: list[Observation] = []

        max_keep = policy.max_active_observations
        for obs, score in scored_obs:
            meta = memory.get_observation_metadata(obs.id)
            if len(retained) < max_keep or (policy.preserve_artifacts and (obs.artifacts or (meta and meta.is_important))):
                retained.append(obs)
            else:
                compacted.append(obs)

        # Preserve original chronological order for retained observations
        original_order = {obs.id: idx for idx, obs in enumerate(memory.observations)}
        retained.sort(key=lambda obs: original_order.get(obs.id, 0))
        return retained, compacted

    def _generate_summary(self, compacted: list[Observation]) -> SummaryBlock:
        """Helper Step 6: Generate SummaryBlock via ISummaryGenerator."""
        return self.summary_generator.generate_summary(compacted)

    def execute(
        self,
        memory: WorkingMemory,
        budget: ContextBudget | None = None,
        policy: RetentionPolicy | None = None,
    ) -> CompactionResult:
        """Execute context compaction algorithm and return CompactionResult delta."""
        active_budget = budget or ContextBudget()
        active_policy = policy or RetentionPolicy()

        current_units = self._estimate(memory)

        if not self._should_compact(current_units, memory, active_budget, active_policy):
            return CompactionResult(
                retained_observations=list(memory.observations),
                compacted_observations=[],
                discarded_observations=[],
                summary_block=SummaryBlock(),
                units_freed=0,
            )

        scored_obs = self._score_observations(memory)
        retained, compacted = self._partition_observations(scored_obs, memory, active_policy)
        summary_block = self._generate_summary(compacted)

        retained_units = sum(self.estimator.estimate_observation(o) for o in retained) + self.estimator.estimate_text(summary_block.text)
        units_freed = max(0, current_units - retained_units)

        return CompactionResult(
            retained_observations=retained,
            compacted_observations=compacted,
            discarded_observations=[],
            summary_block=summary_block,
            units_freed=units_freed,
        )
