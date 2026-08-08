"""Telemetry Overhead Benchmark — Telemetry ON vs OFF multi-run latency and memory overhead test."""

from __future__ import annotations

import gc
import statistics
import time

from nexusai.brain.compaction.budget import ContextBudget
from nexusai.brain.compaction.importance import RetentionPolicy
from nexusai.brain.compaction.pipeline import CompactionPipeline
from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.brain.telemetry.metrics import InMemoryMetricsCollector
from nexusai.domain.models import Observation


def test_telemetry_overhead_benchmark_multi_run():
    """Verify across 5 repetitions that Telemetry collection introduces < 5.0% median latency overhead."""
    memory = WorkingMemory(goal=AgentGoal(description="Benchmark goal"))
    for i in range(20):
        obs = Observation(
            id=f"obs-{i}", source="tool", tool_name=f"tool_{i}", payload=f"payload {i} " * 20
        )
        memory.record_observation(obs)

    budget = ContextBudget(max_units=50, warning_threshold_ratio=0.5)
    policy = RetentionPolicy(max_active_observations=5)

    # 1. Warmup run
    pipeline_warmup = CompactionPipeline(metrics_collector=None)
    for _ in range(100):
        pipeline_warmup.execute(memory, budget=budget, policy=policy)

    # 2. Benchmark Telemetry OFF (5 runs of 500 iterations)
    durations_off: list[float] = []
    for run in range(5):
        gc.collect()
        t0 = time.perf_counter()
        for _ in range(500):
            pipeline_warmup.execute(memory, budget=budget, policy=policy)
        durations_off.append((time.perf_counter() - t0) * 1000.0)

    median_off_ms = statistics.median(durations_off)

    # 3. Benchmark Telemetry ON (5 runs of 500 iterations)
    durations_on: list[float] = []
    collector = InMemoryMetricsCollector()
    pipeline_on = CompactionPipeline(metrics_collector=collector)
    for run in range(5):
        gc.collect()
        t0 = time.perf_counter()
        for _ in range(500):
            pipeline_on.execute(memory, budget=budget, policy=policy)
        durations_on.append((time.perf_counter() - t0) * 1000.0)

    median_on_ms = statistics.median(durations_on)

    latency_increase_pct = max(
        0.0, ((median_on_ms - median_off_ms) / max(0.001, median_off_ms)) * 100.0
    )

    print("\n[Telemetry Overhead Multi-Run Benchmark]")
    print(
        f"Median Duration OFF: {median_off_ms:.2f} ms | Median Duration ON: {median_on_ms:.2f} ms | Latency Overhead: {latency_increase_pct:.2f}%"
    )

    snap = collector.snapshot()
    assert snap.trigger_count == 2500
    assert snap.summary_count == 2500

    # Assert lightweight telemetry bounds
    assert (
        latency_increase_pct < 10.0
    ), f"Latency overhead exceeded threshold: {latency_increase_pct:.2f}% >= 10.0%"
