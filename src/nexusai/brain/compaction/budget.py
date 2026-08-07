"""ContextBudget and pluggable IContextEstimator implementations for NexusAI Agent Runtime.

Strictly provider-independent abstractions measuring context size in abstract ContextUnits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from nexusai.brain.domain.agent import PlanStep
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.core.errors import BrainContextAssemblyError
from nexusai.domain.models import Observation


@dataclass(frozen=True)
class ContextBudget:
    """Provider-independent context ceiling configuration in abstract ContextUnits.

    Attributes:
        max_units: Hard context ceiling in ContextUnits.
        warning_threshold_ratio: Ratio at which context compaction warning triggers (default 0.75).
        critical_threshold_ratio: Ratio at which immediate compaction is forced (default 0.90).
    """

    max_units: int = 32000
    warning_threshold_ratio: float = 0.75
    critical_threshold_ratio: float = 0.90

    def __post_init__(self) -> None:
        """Enforce ContextBudget invariants."""
        if self.max_units <= 0:
            raise BrainContextAssemblyError(
                f"ContextBudget invariant violated: max_units ({self.max_units}) must be positive."
            )
        if not (0.0 < self.warning_threshold_ratio < 1.0):
            raise BrainContextAssemblyError(
                f"ContextBudget invariant violated: warning_threshold_ratio ({self.warning_threshold_ratio}) must be between 0.0 and 1.0."
            )
        if not (0.0 < self.critical_threshold_ratio <= 1.0):
            raise BrainContextAssemblyError(
                f"ContextBudget invariant violated: critical_threshold_ratio ({self.critical_threshold_ratio}) must be between 0.0 and 1.0."
            )
        if self.warning_threshold_ratio >= self.critical_threshold_ratio:
            raise BrainContextAssemblyError(
                f"ContextBudget invariant violated: warning_threshold_ratio ({self.warning_threshold_ratio}) "
                f"must be less than critical_threshold_ratio ({self.critical_threshold_ratio})."
            )

    @property
    def warning_units(self) -> int:
        """Calculate unit threshold for compaction warning."""
        return int(self.max_units * self.warning_threshold_ratio)

    @property
    def critical_units(self) -> int:
        """Calculate unit threshold for critical forced compaction."""
        return int(self.max_units * self.critical_threshold_ratio)


@runtime_checkable
class IContextEstimator(Protocol):
    """Protocol for calculating ContextUnits from observations, steps, or WorkingMemory."""

    def estimate_text(self, text: str) -> int:
        """Estimate ContextUnits for a text payload."""
        ...

    def estimate_observation(self, observation: Observation) -> int:
        """Estimate ContextUnits consumed by an Observation domain entity."""
        ...

    def estimate_step(self, step: PlanStep) -> int:
        """Estimate ContextUnits consumed by a PlanStep domain entity."""
        ...

    def estimate_memory(self, memory: WorkingMemory) -> int:
        """Estimate total ContextUnits consumed by active WorkingMemory snapshot."""
        ...


class CharacterEstimator:
    """Default deterministic estimator mapping character count to ContextUnits (4 chars = 1 unit)."""

    def __init__(self, chars_per_unit: float = 4.0) -> None:
        if chars_per_unit <= 0.0:
            raise ValueError(f"chars_per_unit must be positive, got {chars_per_unit}")
        self.chars_per_unit = chars_per_unit

    def estimate_text(self, text: str) -> int:
        """Estimate units based on character length."""
        if not text:
            return 0
        return max(1, int(len(text) / self.chars_per_unit))

    def estimate_observation(self, observation: Observation) -> int:
        """Estimate units consumed by an Observation."""
        payload_str = str(observation.payload or "")
        tool_str = observation.tool_name or ""
        return self.estimate_text(payload_str) + self.estimate_text(tool_str) + 5

    def estimate_step(self, step: PlanStep) -> int:
        """Estimate units consumed by a PlanStep."""
        content = f"{step.title} {step.description} {step.tool_name or ''} {step.arguments}"
        return self.estimate_text(content) + 5

    def estimate_memory(self, memory: WorkingMemory) -> int:
        """Estimate total units consumed by WorkingMemory."""
        units = self.estimate_text(memory.goal.description)
        for constraint in memory.goal.constraints:
            units += self.estimate_text(constraint)
        for step in memory.steps:
            units += self.estimate_step(step)
        for scratch in memory.scratchpad:
            units += self.estimate_text(scratch)
        for obs in memory.observations:
            units += self.estimate_observation(obs)
        for fail in memory.failures:
            units += self.estimate_text(fail.error_message)
        return units


class ProviderTokenizerEstimator:
    """Adapter bridging to vendor tokenizers or custom callable functions when injected."""

    def __init__(self, tokenizer_fn: Callable[[str], int]) -> None:
        self._tokenizer_fn = tokenizer_fn

    def estimate_text(self, text: str) -> int:
        """Estimate units using injected tokenizer function."""
        if not text:
            return 0
        return max(1, self._tokenizer_fn(text))

    def estimate_observation(self, observation: Observation) -> int:
        """Estimate units consumed by an Observation."""
        payload_str = str(observation.payload or "")
        tool_str = observation.tool_name or ""
        return self.estimate_text(payload_str) + self.estimate_text(tool_str) + 5

    def estimate_step(self, step: PlanStep) -> int:
        """Estimate units consumed by a PlanStep."""
        content = f"{step.title} {step.description} {step.tool_name or ''} {step.arguments}"
        return self.estimate_text(content) + 5

    def estimate_memory(self, memory: WorkingMemory) -> int:
        """Estimate total units consumed by WorkingMemory."""
        units = self.estimate_text(memory.goal.description)
        for constraint in memory.goal.constraints:
            units += self.estimate_text(constraint)
        for step in memory.steps:
            units += self.estimate_step(step)
        for scratch in memory.scratchpad:
            units += self.estimate_text(scratch)
        for obs in memory.observations:
            units += self.estimate_observation(obs)
        for fail in memory.failures:
            units += self.estimate_text(fail.error_message)
        return units
