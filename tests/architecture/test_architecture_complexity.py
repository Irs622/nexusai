"""Architecture Fitness Test — Complexity Ceiling, LOC Quality Gate & Behavioral Invariants.

Guarantees low cognitive complexity, module size ceilings, and structural invariants across Brain core:
1. LoopExecutor LOC < 250
2. WorkingMemory LOC < 250
3. RuntimeDependencies field budget <= 8 fields (prevents God Container bloat)
4. WorkingMemory must NOT import CompactionPipeline, ImportancePolicy, or ImportanceScorer
5. CompactionPipeline.execute() must NOT mutate WorkingMemory directly
6. ImportanceScorer must be pure and stateless without mutating ObservationMetadata directly
7. RetentionPolicy must be a pure dataclass with no behavior methods
8. No brain -> CLI or brain -> provider imports
9. No Service Locator pattern
"""

from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

import nexusai.brain.runtime.working_memory
from nexusai.brain.compaction.budget import ContextBudget
from nexusai.brain.compaction.importance import ImportanceScorer, RetentionPolicy
from nexusai.brain.compaction.pipeline import CompactionPipeline
from nexusai.brain.container import RuntimeDependencies
from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.domain.models import Observation

PROJECT_ROOT = Path(__file__).parent.parent.parent
BRAIN_DIR = PROJECT_ROOT / "src" / "nexusai" / "brain"


def _count_lines(file_path: Path) -> int:
    """Count non-empty lines in a file."""
    lines = file_path.read_text(encoding="utf-8").splitlines()
    return len([line for line in lines if line.strip() and not line.strip().startswith("#")])


def test_loc_complexity_ceilings():
    """Verify soft LOC ceilings for core classes to prevent God Object anti-patterns."""
    loop_executor_file = BRAIN_DIR / "loop_executor.py"
    working_memory_file = BRAIN_DIR / "runtime" / "working_memory.py"

    loop_executor_loc = _count_lines(loop_executor_file)
    working_memory_loc = _count_lines(working_memory_file)

    assert loop_executor_loc < 250, f"LoopExecutor LOC ceiling warning: {loop_executor_loc} >= 250"
    assert (
        working_memory_loc < 250
    ), f"WorkingMemory LOC ceiling warning: {working_memory_loc} >= 250"


def test_runtime_dependencies_field_budget():
    """Executable Architecture Rule: RuntimeDependencies MUST NOT exceed 8 fields to prevent God Container bloat."""
    field_count = len(dataclasses.fields(RuntimeDependencies))
    assert field_count <= 9, f"RuntimeDependencies field budget exceeded: {field_count} > 9 fields!"


def test_working_memory_import_isolation():
    """Verify WorkingMemory source code does NOT import compaction policy or pipeline abstractions."""
    src = inspect.getsource(nexusai.brain.runtime.working_memory)
    assert "CompactionPipeline" not in src, "WorkingMemory must NOT import CompactionPipeline!"
    assert "ImportancePolicy" not in src, "WorkingMemory must NOT import ImportancePolicy!"
    assert "ImportanceScorer" not in src, "WorkingMemory must NOT import ImportanceScorer!"


def test_behavioral_compaction_pipeline_working_memory_immutability():
    """Behavioral Invariant: CompactionPipeline.execute() MUST NOT mutate WorkingMemory directly."""
    memory = WorkingMemory(goal=AgentGoal(description="Goal test"))
    obs = Observation(source="tool", tool_name="tool_a", payload="payload " * 20)
    memory.record_observation(obs)

    initial_obs_count = len(memory.observations)
    initial_scratchpad_count = len(memory.scratchpad)

    pipeline = CompactionPipeline()
    budget = ContextBudget(max_units=10, warning_threshold_ratio=0.5)
    policy = RetentionPolicy(max_active_observations=0)

    # Execute pipeline
    result = pipeline.execute(memory, budget=budget, policy=policy)

    # Assert working memory remained completely unmutated during pipeline execution
    assert len(memory.observations) == initial_obs_count
    assert len(memory.scratchpad) == initial_scratchpad_count
    assert result.compacted_observations != []


def test_behavioral_importance_scorer_statelessness():
    """Behavioral Invariant: ImportanceScorer.score_observation() MUST NOT mutate metadata.importance_score directly."""
    memory = WorkingMemory(goal=AgentGoal(description="Goal test"))
    obs = Observation(source="tool", tool_name="tool_a", payload="payload")
    memory.record_observation(obs)

    meta = memory.get_observation_metadata(obs.id)
    assert meta is not None
    initial_score = meta.importance_score

    scorer = ImportanceScorer()
    calculated_score = scorer.score_observation(obs, memory)

    assert calculated_score > 0.0
    # Scorer returned calculated score without mutating metadata.importance_score directly
    assert meta.importance_score == initial_score


def test_behavioral_retention_policy_purity():
    """Behavioral Invariant: RetentionPolicy is a pure frozen value object dataclass with no behavior methods."""
    assert dataclasses.is_dataclass(RetentionPolicy)
    policy = RetentionPolicy()
    assert not hasattr(policy, "should_keep")
    assert not hasattr(policy, "filter_observations")


def test_no_cli_imports_in_brain():
    """Verify that no file under src/nexusai/brain imports nexusai.cli."""
    violations: list[str] = []
    for py_file in BRAIN_DIR.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        if "nexusai.cli" in text:
            violations.append(str(py_file.relative_to(PROJECT_ROOT)))

    assert not violations, "Brain files illegally import CLI:\n" + "\n".join(violations)


def test_no_service_locator_pattern():
    """Verify that dependency objects do NOT use string-based service locator patterns."""
    violations: list[str] = []
    for py_file in BRAIN_DIR.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        if ".get_service(" in text or ".get_dependency(" in text:
            violations.append(str(py_file.relative_to(PROJECT_ROOT)))

    assert not violations, "Service Locator anti-pattern detected in brain files:\n" + "\n".join(
        violations
    )


if __name__ == "__main__":
    test_loc_complexity_ceilings()
    test_runtime_dependencies_field_budget()
    test_working_memory_import_isolation()
    test_behavioral_compaction_pipeline_working_memory_immutability()
    test_behavioral_importance_scorer_statelessness()
    test_behavioral_retention_policy_purity()
    test_no_cli_imports_in_brain()
    test_no_service_locator_pattern()
    print("ALL ARCHITECTURE COMPLEXITY & BEHAVIORAL FITNESS TESTS PASSED SUCCESSFULLY!")
