"""Unit tests for CompactionPipeline and WorkingMemory.apply_compaction delta integration."""

from nexusai.brain.compaction.budget import ContextBudget
from nexusai.brain.compaction.importance import RetentionPolicy
from nexusai.brain.compaction.pipeline import CompactionPipeline
from nexusai.brain.compaction.result import SummaryBlock
from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.domain.observation_lifecycle import LifecycleState
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.domain.models import Observation


def test_compaction_pipeline_trigger_bypass():
    """Verify CompactionPipeline returns no-op delta when budget is safe."""
    pipeline = CompactionPipeline()
    memory = WorkingMemory(goal=AgentGoal(description="Short goal"))
    obs = Observation(source="tool", tool_name="read_file", payload="short content")
    memory.record_observation(obs)

    budget = ContextBudget(max_units=10000, warning_threshold_ratio=0.75)
    policy = RetentionPolicy(max_active_observations=10)

    result = pipeline.execute(memory, budget=budget, policy=policy)

    assert result.retained_observations == [obs]
    assert result.compacted_observations == []
    assert result.summary_block.text == ""
    assert result.units_freed == 0


def test_compaction_pipeline_execution():
    """Verify CompactionPipeline partition, scoring, summary generation, and application."""
    pipeline = CompactionPipeline()
    memory = WorkingMemory(goal=AgentGoal(description="Goal for compaction"))

    # Record 15 observations (policy max_active_observations = 5)
    observations = []
    for i in range(15):
        obs = Observation(
            id=f"obs-id-{i}",
            source="tool",
            tool_name=f"tool_{i}",
            payload=f"Detailed payload output for step {i} " * 10,
            success=(i % 3 != 0),  # Failure every 3rd step
        )
        memory.record_observation(obs)
        observations.append(obs)

    # Budget with low max_units to force trigger
    budget = ContextBudget(max_units=100, warning_threshold_ratio=0.5)
    policy = RetentionPolicy(max_active_observations=5, preserve_artifacts=True)

    result = pipeline.execute(memory, budget=budget, policy=policy)

    assert len(result.retained_observations) == 5
    assert len(result.compacted_observations) == 10
    assert isinstance(result.summary_block, SummaryBlock)
    assert "[Context Summary:" in result.summary_block.text

    # Apply compaction to WorkingMemory
    memory.apply_compaction(result)

    assert len(memory.observations) == 5
    assert str(result.summary_block) in memory.scratchpad

    # Compacted observations metadata state updated
    for obs in result.compacted_observations:
        meta = memory.get_observation_metadata(obs.id)
        assert meta is not None
        assert meta.state == LifecycleState.COMPACTED
