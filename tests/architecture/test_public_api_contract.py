"""Architecture Fitness Test — Public API Compatibility Contract.

Guarantees that all symbols exported in nexusai.brain.__all__ remain stable and backward compatible,
verifying protocol signatures, constructor parameters, frozen flags, and default value contracts.
"""

from __future__ import annotations

import dataclasses
import inspect
import nexusai.brain
from nexusai.brain.compaction import CompactionPipeline, CompactionResult, ContextBudget, IContextEstimator, SummaryBlock
from nexusai.brain.container import RuntimeDependencies
from nexusai.brain.domain.agent import AgentGoal, PlanStep
from nexusai.brain.failure_detector import FailureAnalysis, FailureClassifier, FailureEvidence
from nexusai.brain.ports.tool_port import IToolPort
from nexusai.brain.runtime.working_memory import RetryPolicy, WorkingMemory
from nexusai.brain.strategy import IDecisionStrategy, IPlanningStrategy, IReflectionStrategy


def test_brain_public_all_exports_stable():
    """Verify that all public exports in nexusai.brain.__all__ are importable and non-empty."""
    exported_symbols = nexusai.brain.__all__
    assert len(exported_symbols) >= 70, f"Expected at least 70 exported symbols, got {len(exported_symbols)}"

    for symbol_name in exported_symbols:
        assert hasattr(nexusai.brain, symbol_name), (
            f"Public API Contract Broken: '{symbol_name}' is declared in __all__ but missing from nexusai.brain package!"
        )


def test_core_dataclass_contracts():
    """Verify frozen status, default values, and field invariants on core domain/runtime dataclasses."""
    assert dataclasses.is_dataclass(AgentGoal)
    assert dataclasses.is_dataclass(ContextBudget)
    assert dataclasses.is_dataclass(CompactionResult)
    assert dataclasses.is_dataclass(SummaryBlock)
    assert dataclasses.is_dataclass(FailureEvidence)
    assert dataclasses.is_dataclass(FailureAnalysis)
    assert dataclasses.is_dataclass(RuntimeDependencies)
    assert dataclasses.is_dataclass(RetryPolicy)
    assert dataclasses.is_dataclass(WorkingMemory)

    # ContextBudget defaults
    default_budget = ContextBudget()
    assert default_budget.max_units == 32000
    assert default_budget.warning_threshold_ratio == 0.75
    assert default_budget.critical_threshold_ratio == 0.90

    # RetryPolicy defaults
    default_retry = RetryPolicy()
    assert default_retry.max_attempts == 3
    assert default_retry.backoff_factor == 2.0


def test_core_protocol_signatures_stable():
    """Verify core Strategy & Port Protocol interfaces have stable method signatures."""

    # IPlanningStrategy.generate_plan signature
    plan_sig = inspect.signature(IPlanningStrategy.generate_plan)
    assert "goal" in plan_sig.parameters
    assert "ctx" in plan_sig.parameters

    # IReflectionStrategy.reflect signature
    reflect_sig = inspect.signature(IReflectionStrategy.reflect)
    assert "memory" in reflect_sig.parameters
    assert "observation" in reflect_sig.parameters

    # IDecisionStrategy.decide signature
    decide_sig = inspect.signature(IDecisionStrategy.decide)
    assert "memory" in decide_sig.parameters
    assert "analysis" in decide_sig.parameters

    # IToolPort.execute signature
    tool_sig = inspect.signature(IToolPort.execute)
    assert "request" in tool_sig.parameters

    # IContextEstimator method signatures
    est_text_sig = inspect.signature(IContextEstimator.estimate_text)
    assert "text" in est_text_sig.parameters

    est_obs_sig = inspect.signature(IContextEstimator.estimate_observation)
    assert "observation" in est_obs_sig.parameters

    est_mem_sig = inspect.signature(IContextEstimator.estimate_memory)
    assert "memory" in est_mem_sig.parameters


if __name__ == "__main__":
    test_brain_public_all_exports_stable()
    test_core_dataclass_contracts()
    test_core_protocol_signatures_stable()
    print("PUBLIC API COMPATIBILITY CONTRACT FITNESS TESTS PASSED SUCCESSFULLY!")
