"""Unit tests for Runtime Telemetry (IMetricsCollector & InMemoryMetricsCollector)."""

from nexusai.brain.compaction.budget import ContextBudget
from nexusai.brain.compaction.importance import RetentionPolicy
from nexusai.brain.compaction.pipeline import CompactionPipeline
from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.brain.telemetry.metrics import InMemoryMetricsCollector
from nexusai.domain.models import Observation


def test_in_memory_metrics_collector_record_and_snapshot():
    """Verify InMemoryMetricsCollector records compaction and failure events and generates accurate snapshots."""
    collector = InMemoryMetricsCollector()

    # Record safe bypass (was_triggered=False)
    collector.record_compaction(
        duration_ms=1.5,
        units_before=50,
        units_after=50,
        obs_before=2,
        obs_after=2,
        was_triggered=False,
        summary_created=False,
    )

    # Record triggered compaction
    collector.record_compaction(
        duration_ms=12.4,
        units_before=500,
        units_after=200,
        obs_before=15,
        obs_after=5,
        was_triggered=True,
        summary_created=True,
    )

    # Record failures
    collector.record_failure(category="NETWORK", tool_name="fetch_web")
    collector.record_failure(category="PERMISSION", tool_name="fs_write")

    snapshot = collector.snapshot()

    assert snapshot.skipped_count == 1
    assert snapshot.trigger_count == 1
    assert snapshot.failures_count == 2
    assert snapshot.summary_count == 1
    assert snapshot.total_units_before == 500
    assert snapshot.total_units_after == 200
    assert snapshot.total_units_saved == 300
    assert snapshot.total_observations_before == 15
    assert snapshot.total_observations_after == 5
    assert snapshot.failures_by_category["NETWORK"] == 1
    assert snapshot.failures_by_category["PERMISSION"] == 1
    assert snapshot.total_duration_ms == 13.9
    assert snapshot.average_duration_ms == 6.95


def test_compaction_pipeline_telemetry_integration():
    """Verify CompactionPipeline automatically records telemetry via injected IMetricsCollector."""
    collector = InMemoryMetricsCollector()
    pipeline = CompactionPipeline(metrics_collector=collector)

    memory = WorkingMemory(goal=AgentGoal(description="Telemetry integration test goal"))
    for i in range(12):
        obs = Observation(
            id=f"obs-{i}",
            source="tool",
            tool_name=f"tool_{i}",
            payload=f"Detailed payload data {i} " * 10,
        )
        memory.record_observation(obs)

    budget = ContextBudget(max_units=50, warning_threshold_ratio=0.5)
    policy = RetentionPolicy(max_active_observations=4)

    result = pipeline.execute(memory, budget=budget, policy=policy)
    assert len(result.retained_observations) == 4

    snap = collector.snapshot()
    assert snap.trigger_count == 1
    assert snap.summary_count == 1
    assert snap.total_units_saved > 0
    assert snap.total_observations_before == 12
    assert snap.total_observations_after == 4
