"""
Unit tests for RequiredCapabilities, Capability enum, ExecutionConstraints, ExecutionStep, ExecutionPlan, and ProviderSelector.
"""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

from nexusai.brain.domain import SchemaVersion
from nexusai.brain.runtime import (
    Capability,
    ExecutionConstraints,
    ExecutionPlan,
    ExecutionStep,
    ProviderSelector,
    RequiredCapabilities,
)
from nexusai.core.errors import BrainCapabilityNegotiationError


def test_required_capabilities_and_constraints() -> None:
    """Verify RequiredCapabilities, Capability Enum, ExecutionConstraints, and immutability."""
    constraints = ExecutionConstraints(min_context_window=64000, prefer_local=True)
    caps = RequiredCapabilities(
        capabilities=[Capability.VISION, Capability.JSON_MODE],
        constraints=constraints,
    )

    assert isinstance(caps.capabilities, tuple)
    assert caps.has_capability(Capability.VISION) is True
    assert caps.has_capability("vision") is True
    assert caps.has_capability(Capability.AUDIO) is False
    assert caps.constraints.prefer_local is True

    with pytest.raises(FrozenInstanceError):
        caps.constraints = ExecutionConstraints()  # type: ignore[misc]

    d = caps.to_dict()
    restored = RequiredCapabilities.from_dict(d)
    assert restored.has_capability(Capability.VISION) is True
    assert restored.constraints.prefer_local is True


def test_execution_plan_invariants_and_serialization() -> None:
    """Verify ExecutionPlan invariants, primary step retrieval, and serialization boundaries."""
    step1 = ExecutionStep(step_type="provider_invocation", provider_id="openrouter", model_id="claude-3.5-sonnet")
    step2 = ExecutionStep(step_type="fallback_invocation", provider_id="gemini", model_id="gemini-1.5-pro")

    plan = ExecutionPlan(steps=[step1], fallback_chain=[step2])

    assert plan.plan_version == SchemaVersion(1, 0)
    assert isinstance(plan.steps, tuple)
    assert isinstance(plan.fallback_chain, tuple)
    assert plan.primary_step == step1

    with pytest.raises(BrainCapabilityNegotiationError, match="must contain at least one primary execution step"):
        ExecutionPlan(steps=[])

    d = plan.to_dict()
    restored = ExecutionPlan.from_dict(d)
    assert restored.primary_step.provider_id == "openrouter"
    assert len(restored.fallback_chain) == 1


def test_provider_selector_capability_negotiation() -> None:
    """Verify ProviderSelector builds ExecutionPlan with appropriate primary and fallback routes."""
    selector = ProviderSelector()
    caps = RequiredCapabilities(
        capabilities=[Capability.VISION, Capability.JSON_MODE],
        constraints=ExecutionConstraints(prefer_local=False),
    )

    plan = selector.select_plan(capabilities=caps, preferred_provider="anthropic")

    assert plan.primary_step.provider_id == "anthropic"
    assert len(plan.fallback_chain) >= 1

    # Local model preference test via ExecutionConstraints
    local_caps = RequiredCapabilities(
        capabilities=[Capability.VISION],
        constraints=ExecutionConstraints(prefer_local=True),
    )
    local_plan = selector.select_plan(capabilities=local_caps)
    assert local_plan.primary_step.provider_id == "ollama"
