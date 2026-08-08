"""
ExecutionStep and ExecutionPlan strategy containers returned by ProviderSelector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from nexusai.brain.domain.version import SchemaVersion
from nexusai.core.errors import BrainCapabilityNegotiationError


@dataclass(frozen=True)
class ExecutionStep:
    """Represents a single executable step within an ExecutionPlan.

    Attributes:
        step_id: Unique step identifier.
        step_type: Type of step (e.g. 'provider_invocation', 'prompt_cache', 'fallback_invocation').
        provider_id: Target model provider ID (e.g. 'anthropic', 'openrouter', 'ollama').
        model_id: Target specific model ID (e.g. 'claude-3.5-sonnet').
        parameters: Optional step-specific parameters.
    """

    step_id: str = field(default_factory=lambda: uuid4().hex[:8])
    step_type: str = "provider_invocation"
    provider_id: str = "openrouter"
    model_id: str = "default-model"
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize ExecutionStep to dictionary format."""
        return {
            "step_id": self.step_id,
            "step_type": self.step_type,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionStep:
        """Deserialize ExecutionStep from dictionary format."""
        return cls(
            step_id=str(data.get("step_id", uuid4().hex[:8])),
            step_type=str(data.get("step_type", "provider_invocation")),
            provider_id=str(data.get("provider_id", "openrouter")),
            model_id=str(data.get("model_id", "default-model")),
            parameters=dict(data.get("parameters", {})),
        )


@dataclass(frozen=True)
class ExecutionPlan:
    """Immutable execution strategy container directing how a turn is executed.

    Attributes:
        plan_id: Unique UUID identifier for the plan.
        plan_version: Schema contract version.
        steps: Tuple of primary execution steps.
        fallback_chain: Tuple of fallback execution steps if primary steps fail.
    """

    plan_id: UUID = field(default_factory=uuid4)
    plan_version: SchemaVersion = field(default_factory=SchemaVersion)
    steps: tuple[ExecutionStep, ...] = field(default_factory=tuple)
    fallback_chain: tuple[ExecutionStep, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Enforce ExecutionPlan domain invariants."""
        if isinstance(self.steps, list):
            object.__setattr__(self, "steps", tuple(self.steps))
        if isinstance(self.fallback_chain, list):
            object.__setattr__(self, "fallback_chain", tuple(self.fallback_chain))

        if not self.steps:
            raise BrainCapabilityNegotiationError(
                "ExecutionPlan invariant violated: plan must contain at least one primary execution step."
            )

    @property
    def primary_step(self) -> ExecutionStep:
        """Get the primary execution step."""
        return self.steps[0]

    def to_dict(self) -> dict[str, Any]:
        """Serialize ExecutionPlan to dictionary format."""
        return {
            "plan_id": str(self.plan_id),
            "plan_version": self.plan_version.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
            "fallback_chain": [step.to_dict() for step in self.fallback_chain],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionPlan:
        """Deserialize ExecutionPlan from dictionary format."""
        version_data = data.get("plan_version", {})
        plan_version = (
            SchemaVersion.from_dict(version_data)
            if isinstance(version_data, dict)
            else SchemaVersion()
        )
        steps = tuple(ExecutionStep.from_dict(s) for s in data.get("steps", []))
        fallback_chain = tuple(ExecutionStep.from_dict(s) for s in data.get("fallback_chain", []))

        return cls(
            plan_id=UUID(data["plan_id"]) if "plan_id" in data else uuid4(),
            plan_version=plan_version,
            steps=steps,
            fallback_chain=fallback_chain,
        )
