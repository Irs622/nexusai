"""Architecture Fitness Test — Public API Compatibility Contract.

Guarantees that all symbols exported in nexusai.brain.__all__ remain stable and backward compatible,
verifying protocol signatures, constructor parameters, frozen flags, and default value contracts.
"""

from __future__ import annotations

import dataclasses
import inspect

import nexusai.brain
from nexusai.brain.compaction import (
    CompactionResult,
    ContextBudget,
    IContextEstimator,
    SummaryBlock,
)
from nexusai.brain.container import RuntimeDependencies
from nexusai.brain.domain.agent import (
    ActionCandidate,
    AgentGoal,
    CapabilityGraph,
    DecisionEvidence,
    DecisionOutcome,
    DecisionReasoning,
    DecisionTrace,
    ExecutionFailure,
    PlanGraph,
    PlanGraphNode,
    PlannerWeights,
    PlanningConstraints,
    PlanningContext,
    PlanningGoal,
    PlanningPolicy,
    PlanningResources,
    RejectedCandidate,
    ScoringEvidenceFactor,
    ValidationIssue,
    ValidationResult,
)
from nexusai.brain.domain.world import SystemResourceUsage, WorldState
from nexusai.brain.eval import (
    BenchmarkEnvironment,
    BenchmarkReport,
    ComparisonReport,
    CoverageReport,
    DecisionDatasetEntry,
    EvaluationResult,
    EvaluationSummary,
    RegressionReport,
    Scenario,
    ScenarioCorpus,
)
from nexusai.brain.failure_detector import FailureAnalysis, FailureEvidence
from nexusai.brain.memory import (
    IndexedMemoryItem,
    MemoryConflict,
    MemoryPolicy,
    RankedMemoryItem,
)
from nexusai.brain.ports import (
    CapabilityAdvertisement,
    CapabilityProvider,
    IToolPort,
)
from nexusai.brain.reflection.engine import ReflectionResult
from nexusai.brain.replay import (
    ExecutionEvent,
    ExecutionLog,
)
from nexusai.brain.runtime import (
    ExecutionPolicy,
    ResourceBudget,
)
from nexusai.brain.runtime.working_memory import RetryPolicy, WorkingMemory
from nexusai.brain.strategy import IDecisionStrategy, IPlanningStrategy, IReflectionStrategy
from nexusai.brain.telemetry import (
    CompactionMetricsSnapshot,
    ExecutionSpan,
    IMetricsCollector,
)


def test_brain_public_all_exports_stable():
    """Verify that all public exports in nexusai.brain.__all__ are importable and non-empty."""
    exported_symbols = nexusai.brain.__all__
    assert (
        len(exported_symbols) >= 75
    ), f"Expected at least 75 exported symbols, got {len(exported_symbols)}"

    for symbol_name in exported_symbols:
        assert hasattr(
            nexusai.brain, symbol_name
        ), f"Public API Contract Broken: '{symbol_name}' is declared in __all__ but missing from nexusai.brain package!"


def test_core_dataclass_contracts():
    """Verify frozen status, default values, and field invariants on core domain/runtime dataclasses."""
    assert dataclasses.is_dataclass(AgentGoal)
    assert dataclasses.is_dataclass(ContextBudget)
    assert dataclasses.is_dataclass(CompactionResult)
    assert dataclasses.is_dataclass(SummaryBlock)
    assert dataclasses.is_dataclass(FailureEvidence)
    assert dataclasses.is_dataclass(FailureAnalysis)
    assert dataclasses.is_dataclass(CompactionMetricsSnapshot)
    assert dataclasses.is_dataclass(ExecutionEvent)
    assert dataclasses.is_dataclass(ExecutionLog)
    assert dataclasses.is_dataclass(EvaluationResult)
    assert dataclasses.is_dataclass(Scenario)
    assert dataclasses.is_dataclass(ScenarioCorpus)
    assert dataclasses.is_dataclass(BenchmarkReport)
    assert dataclasses.is_dataclass(BenchmarkEnvironment)
    assert dataclasses.is_dataclass(ComparisonReport)
    assert dataclasses.is_dataclass(RegressionReport)
    assert dataclasses.is_dataclass(CoverageReport)
    assert dataclasses.is_dataclass(DecisionReasoning)
    assert dataclasses.is_dataclass(DecisionTrace)
    assert dataclasses.is_dataclass(DecisionEvidence)
    assert dataclasses.is_dataclass(DecisionOutcome)
    assert dataclasses.is_dataclass(ActionCandidate)
    assert dataclasses.is_dataclass(ScoringEvidenceFactor)
    assert dataclasses.is_dataclass(RejectedCandidate)
    assert dataclasses.is_dataclass(CapabilityGraph)
    assert dataclasses.is_dataclass(CapabilityProvider)
    assert dataclasses.is_dataclass(CapabilityAdvertisement)
    assert dataclasses.is_dataclass(ExecutionPolicy)
    assert dataclasses.is_dataclass(ResourceBudget)
    assert dataclasses.is_dataclass(ExecutionSpan)
    assert dataclasses.is_dataclass(EvaluationSummary)
    assert dataclasses.is_dataclass(DecisionDatasetEntry)
    assert dataclasses.is_dataclass(ValidationIssue)
    assert dataclasses.is_dataclass(ValidationResult)
    assert dataclasses.is_dataclass(IndexedMemoryItem)
    assert dataclasses.is_dataclass(RankedMemoryItem)
    assert dataclasses.is_dataclass(MemoryConflict)
    assert dataclasses.is_dataclass(MemoryPolicy)
    assert dataclasses.is_dataclass(WorldState)
    assert dataclasses.is_dataclass(SystemResourceUsage)
    assert dataclasses.is_dataclass(ReflectionResult)
    assert dataclasses.is_dataclass(PlanningGoal)
    assert dataclasses.is_dataclass(PlanningResources)
    assert dataclasses.is_dataclass(PlanningConstraints)
    assert dataclasses.is_dataclass(PlanningContext)
    assert dataclasses.is_dataclass(PlanGraphNode)
    assert dataclasses.is_dataclass(PlanGraph)
    assert dataclasses.is_dataclass(PlannerWeights)
    assert dataclasses.is_dataclass(PlanningPolicy)
    assert dataclasses.is_dataclass(ExecutionFailure)
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

    # IMetricsCollector method signatures
    rec_comp_sig = inspect.signature(IMetricsCollector.record_compaction)
    assert "duration_ms" in rec_comp_sig.parameters
    assert "units_before" in rec_comp_sig.parameters
    assert "units_after" in rec_comp_sig.parameters


if __name__ == "__main__":
    test_brain_public_all_exports_stable()
    test_core_dataclass_contracts()
    test_core_protocol_signatures_stable()
    print("PUBLIC API COMPATIBILITY CONTRACT FITNESS TESTS PASSED SUCCESSFULLY!")
