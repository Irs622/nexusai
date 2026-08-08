"""Unit tests for RetentionPolicy, ImportancePolicy, and ImportanceScorer."""

from nexusai.brain.compaction.importance import (
    ImportanceScorer,
    LinearPolicy,
    RetentionPolicy,
    RulePolicy,
)
from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.domain.observation_lifecycle import ObservationMetadata
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.domain.models import Observation


def test_retention_policy_defaults():
    """Verify RetentionPolicy default configuration values."""
    policy = RetentionPolicy()
    assert policy.max_active_observations == 10
    assert policy.max_failure_records == 5
    assert policy.preserve_artifacts is True
    assert policy.max_summary_units == 500


def test_linear_policy_evaluation():
    """Verify LinearPolicy feature weights and scoring."""
    policy = LinearPolicy()
    memory = WorkingMemory(goal=AgentGoal(description="Goal test"))

    obs_normal = Observation(source="tool", tool_name="read_file", payload="content", success=True)
    obs_failure = Observation(
        source="tool", tool_name="read_file", payload="error", success=False, severity="ERROR"
    )
    obs_write = Observation(source="tool", tool_name="write_file", payload="written", success=True)

    memory.record_observation(obs_normal)
    memory.record_observation(obs_failure)
    memory.record_observation(obs_write)

    scorer = ImportanceScorer(policy=policy)
    score_normal = scorer.score_observation(obs_normal, memory)
    score_failure = scorer.score_observation(obs_failure, memory)
    score_write = scorer.score_observation(obs_write, memory)

    assert 0.0 <= score_normal <= 1.0
    assert 0.0 <= score_failure <= 1.0
    assert 0.0 <= score_write <= 1.0

    # Failure observation score should be higher than normal read observation
    assert score_failure > score_normal


def test_rule_policy_evaluation():
    """Verify RulePolicy deterministic rules priority."""
    policy = RulePolicy()
    memory = WorkingMemory(goal=AgentGoal(description="Goal test"))

    obs_important = Observation(source="tool", tool_name="tool_a", payload="output")
    meta_important = ObservationMetadata(observation_id=obs_important.id, is_important=True)
    memory.record_observation(obs_important, metadata=meta_important)

    obs_failed = Observation(source="tool", tool_name="tool_b", payload="failed", success=False)
    memory.record_observation(obs_failed)

    scorer = ImportanceScorer(policy=policy)
    assert scorer.score_observation(obs_important, memory) == 1.0
    assert scorer.score_observation(obs_failed, memory) == 0.9
