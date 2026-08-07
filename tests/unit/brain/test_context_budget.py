"""Unit tests for ContextBudget and pluggable IContextEstimator implementations."""

import pytest
from nexusai.brain.compaction.budget import (
    CharacterEstimator,
    ContextBudget,
    IContextEstimator,
    ProviderTokenizerEstimator,
)
from nexusai.brain.domain.agent import AgentGoal, PlanStep
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.core.errors import BrainContextAssemblyError
from nexusai.domain.models import Observation


def test_context_budget_invariants():
    """Verify ContextBudget validation invariants."""
    budget = ContextBudget(max_units=10000, warning_threshold_ratio=0.7, critical_threshold_ratio=0.85)
    assert budget.max_units == 10000
    assert budget.warning_units == 7000
    assert budget.critical_units == 8500

    with pytest.raises(BrainContextAssemblyError, match="max_units .* must be positive"):
        ContextBudget(max_units=0)

    with pytest.raises(BrainContextAssemblyError, match="warning_threshold_ratio .* must be between 0.0 and 1.0"):
        ContextBudget(warning_threshold_ratio=1.5)

    with pytest.raises(BrainContextAssemblyError, match="warning_threshold_ratio .* must be less than critical_threshold_ratio"):
        ContextBudget(warning_threshold_ratio=0.9, critical_threshold_ratio=0.8)


def test_character_estimator():
    """Verify CharacterEstimator calculation rules."""
    estimator = CharacterEstimator(chars_per_unit=4.0)
    assert isinstance(estimator, IContextEstimator)

    assert estimator.estimate_text("") == 0
    assert estimator.estimate_text("12345678") == 2

    obs = Observation(source="tool", tool_name="workspace_read", payload="file content string")
    assert estimator.estimate_observation(obs) > 0

    step = PlanStep(step_id=1, title="Test", description="Step description")
    assert estimator.estimate_step(step) > 0

    memory = WorkingMemory(goal=AgentGoal(description="Goal test"))
    memory.add_scratchpad_entry("Thinking about solution")
    memory.record_observation(obs)
    assert estimator.estimate_memory(memory) > 0


def test_provider_tokenizer_estimator():
    """Verify ProviderTokenizerEstimator with custom injected tokenizer function."""
    def mock_tokenizer(text: str) -> int:
        return len(text.split())

    estimator = ProviderTokenizerEstimator(tokenizer_fn=mock_tokenizer)
    assert isinstance(estimator, IContextEstimator)

    assert estimator.estimate_text("one two three four") == 4
    assert estimator.estimate_text("") == 0

    obs = Observation(source="tool", tool_name="workspace_read", payload="hello world")
    assert estimator.estimate_observation(obs) == (2 + 1 + 5)
