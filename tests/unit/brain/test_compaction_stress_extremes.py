"""Failure-Oriented Stress & Extreme Boundary Unit Tests for Context Compaction."""

from nexusai.brain.compaction.budget import ContextBudget
from nexusai.brain.compaction.importance import RetentionPolicy
from nexusai.brain.compaction.pipeline import CompactionPipeline
from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.domain.models import Observation


def test_extreme_all_artifact_observations():
    """Extreme Boundary: All observations are artifact-generating observations."""
    pipeline = CompactionPipeline()
    memory = WorkingMemory(goal=AgentGoal(description="Artifact stress goal"))

    for i in range(20):
        obs = Observation(
            id=f"art-obs-{i}",
            source="tool",
            tool_name="generate_image",
            payload=f"Artifact payload {i}",
            artifacts=[f"artifact_{i}.png"],
        )
        memory.record_observation(obs)

    budget = ContextBudget(max_units=50, warning_threshold_ratio=0.5)
    policy = RetentionPolicy(max_active_observations=5, preserve_artifacts=True)

    result = pipeline.execute(memory, budget=budget, policy=policy)

    # When preserve_artifacts=True, all artifact observations are protected
    assert len(result.retained_observations) == 20
    assert len(result.compacted_observations) == 0


def test_extreme_all_failures():
    """Extreme Boundary: All observations are failures."""
    pipeline = CompactionPipeline()
    memory = WorkingMemory(goal=AgentGoal(description="Failure stress goal"))

    for i in range(15):
        obs = Observation(
            id=f"fail-obs-{i}",
            source="tool",
            tool_name="cmd_tool",
            payload=f"Error message output {i}",
            success=False,
            severity="ERROR",
        )
        memory.record_observation(obs)

    budget = ContextBudget(max_units=50, warning_threshold_ratio=0.5)
    policy = RetentionPolicy(max_active_observations=5, preserve_artifacts=False)

    result = pipeline.execute(memory, budget=budget, policy=policy)

    assert len(result.retained_observations) == 5
    assert len(result.compacted_observations) == 10
    memory.apply_compaction(result)
    assert len(memory.observations) == 5


def test_extreme_large_payload_observations():
    """Extreme Boundary: 1 MB large payload observation processing."""
    pipeline = CompactionPipeline()
    memory = WorkingMemory(goal=AgentGoal(description="Large payload goal"))

    large_payload = "X" * 1_000_000  # 1 MB text
    obs_large = Observation(source="tool", tool_name="big_read", payload=large_payload)
    obs_normal = Observation(source="tool", tool_name="small_read", payload="small")

    memory.record_observation(obs_large)
    memory.record_observation(obs_normal)

    budget = ContextBudget(max_units=50, warning_threshold_ratio=0.5)
    policy = RetentionPolicy(max_active_observations=1)

    result = pipeline.execute(memory, budget=budget, policy=policy)

    assert len(result.retained_observations) == 1
    assert result.units_freed > 100000
