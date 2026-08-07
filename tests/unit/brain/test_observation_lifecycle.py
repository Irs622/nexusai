"""Comprehensive Invariant & Lifecycle State Transition Unit Tests."""

import pytest
from nexusai.brain.compaction.result import CompactionResult
from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.domain.observation_lifecycle import (
    InvalidLifecycleTransitionError,
    LifecycleState,
    ObservationMetadata,
)
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.core.errors import DuplicateObservationError
from nexusai.domain.models import Observation


def test_valid_lifecycle_transitions():
    """Verify legal state transitions: ACTIVE -> COMPACTED -> ARCHIVED."""
    meta = ObservationMetadata(observation_id="obs-1")
    assert meta.state == LifecycleState.ACTIVE

    meta.mark_compacted()
    assert meta.state == LifecycleState.COMPACTED

    meta.mark_archived()
    assert meta.state == LifecycleState.ARCHIVED


def test_invalid_lifecycle_transitions():
    """Verify illegal transitions raise InvalidLifecycleTransitionError."""
    meta = ObservationMetadata(observation_id="obs-2")
    meta.mark_archived()
    assert meta.state == LifecycleState.ARCHIVED

    # Cannot transition from ARCHIVED to ACTIVE or COMPACTED
    with pytest.raises(InvalidLifecycleTransitionError, match="Invalid ObservationMetadata lifecycle transition"):
        meta.transition_to(LifecycleState.ACTIVE)

    with pytest.raises(InvalidLifecycleTransitionError):
        meta.transition_to(LifecycleState.COMPACTED)


def test_every_observation_has_one_metadata():
    """Invariant: Every Observation in WorkingMemory MUST have exactly one ObservationMetadata."""
    obs1 = Observation(source="tool", tool_name="tool_a", payload="output 1")
    obs2 = Observation(source="tool", tool_name="tool_b", payload="output 2")

    memory = WorkingMemory(goal=AgentGoal(description="Goal test"), observations=[obs1])
    assert memory.has_observation_metadata(obs1.id)
    assert memory.get_observation_metadata(obs1.id) is not None

    memory.record_observation(obs2)
    assert memory.has_observation_metadata(obs2.id)
    assert memory.get_observation_metadata(obs2.id) is not None


def test_duplicate_observation_id_rejected():
    """Invariant: Duplicate observation IDs are rejected with DuplicateObservationError."""
    obs1 = Observation(id="fixed-id-100", source="tool", tool_name="tool_a", payload="output 1")
    obs1_dup = Observation(id="fixed-id-100", source="tool", tool_name="tool_a", payload="output 2")

    memory = WorkingMemory(goal=AgentGoal(description="Goal test"))
    memory.record_observation(obs1)

    with pytest.raises(DuplicateObservationError, match="Duplicate observation ID .* rejected"):
        memory.record_observation(obs1_dup)


def test_observation_removal_cleans_metadata():
    """Invariant: Removing an observation cleans up metadata to prevent orphans."""
    obs1 = Observation(source="tool", tool_name="tool_a", payload="output 1")
    memory = WorkingMemory(goal=AgentGoal(description="Goal test"))
    memory.record_observation(obs1)

    assert memory.has_observation_metadata(obs1.id)

    removed = memory.remove_observation(obs1.id)
    assert removed == obs1
    assert not memory.has_observation_metadata(obs1.id)


def test_apply_compaction_maintains_invariants():
    """Invariant: apply_compaction(CompactionResult) updates retained, compacted, and discarded metadata."""
    obs_retained = Observation(source="tool", tool_name="tool_a", payload="retained")
    obs_compacted = Observation(source="tool", tool_name="tool_b", payload="compacted")
    obs_discarded = Observation(source="tool", tool_name="tool_c", payload="discarded")

    memory = WorkingMemory(goal=AgentGoal(description="Goal test"))
    memory.record_observation(obs_retained)
    memory.record_observation(obs_compacted)
    memory.record_observation(obs_discarded)

    result = CompactionResult(
        retained_observations=[obs_retained],
        compacted_observations=[obs_compacted],
        discarded_observations=[obs_discarded],
        summary_block="Compaction summary of tool_b.",
        units_freed=50,
    )

    memory.apply_compaction(result)

    assert memory.observations == [obs_retained]
    assert memory.get_observation_metadata(obs_retained.id).state == LifecycleState.ACTIVE
    assert memory.get_observation_metadata(obs_compacted.id).state == LifecycleState.COMPACTED
    assert not memory.has_observation_metadata(obs_discarded.id)  # Cleaned up, no orphan
    assert "Compaction summary of tool_b." in memory.scratchpad
