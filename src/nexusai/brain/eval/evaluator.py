"""Standardized Agent Evaluation Data Model and Evaluator for NexusAI Runtime."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from nexusai.brain.replay.serialization import ExecutionLog, compute_core_state_hash
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.brain.telemetry.metrics import CompactionMetricsSnapshot, InMemoryMetricsCollector


@dataclass(frozen=True)
class EvaluationResult:  # type: ignore[no-redef]
    """Standardized evaluation report output measuring quality across a scenario execution run.

    Attributes:
        scenario_id: Scenario UUID or identifier string.
        success: Overall boolean success flag.
        task_completion_rate: Ratio of completed steps vs total planned steps (0.0 to 1.0).
        decision_score: Calculated agent decision quality score (0.0 to 1.0).
        latency_ms: Total scenario execution duration in milliseconds.
        memory_delta_kb: Memory consumption delta in KB.
        tool_success_rate: Ratio of successful tool calls vs total tool calls (0.0 to 1.0).
        recovery_turns: Number of turn iterations executed to recover from failures.
        metrics_snapshot: Accumulated CompactionMetricsSnapshot telemetry.
        replay_hash: Deterministic core state hash string produced by replay.
        evaluation_version: Version integer of the evaluator algorithm (default 1).
        timestamp: Epoch timestamp float when evaluation occurred.
    """

    scenario_id: str
    success: bool
    task_completion_rate: float = 1.0
    decision_score: float = 1.0
    latency_ms: float = 0.0
    memory_delta_kb: float = 0.0
    tool_success_rate: float = 1.0
    recovery_turns: int = 0
    metrics_snapshot: CompactionMetricsSnapshot = field(default_factory=CompactionMetricsSnapshot)
    replay_hash: str = ""
    expected_state_hash: str = ""
    actual_state_hash: str = ""
    evaluation_version: int = 1
    timestamp: float = field(default_factory=time.time)

    @property
    def needs_retry(self) -> bool:
        """Computed property indicating whether retry is recommended."""
        return not self.success


class AgentEvaluator:
    """Evaluates WorkingMemory execution snapshots and generates standardized EvaluationResult reports."""

    def evaluate(
        self,
        scenario_id: str,
        memory: WorkingMemory,
        log: ExecutionLog | None = None,
        collector: InMemoryMetricsCollector | None = None,
        latency_ms: float = 0.0,
    ) -> EvaluationResult:
        """Calculate standardized EvaluationResult report."""
        total_steps = len(memory.steps)
        completed_steps = sum(1 for s in memory.steps if s.status.value == "COMPLETED")
        task_completion = completed_steps / max(1, total_steps)

        obs_successes = sum(1 for o in memory.observations if o.success)
        total_obs = len(memory.observations)
        tool_success_rate = obs_successes / max(1, total_obs)

        _failures_count = len(memory.failures)
        recovery_turns = memory.retry_count

        state_hash = compute_core_state_hash(memory)
        metrics_snap = collector.snapshot() if collector else CompactionMetricsSnapshot()

        success = (
            task_completion >= 0.8
            and tool_success_rate >= 0.5
            and (not log or not log.expected_state_hash or log.expected_state_hash == state_hash)
        )

        return EvaluationResult(
            scenario_id=scenario_id,
            success=success,
            task_completion_rate=round(task_completion, 2),
            decision_score=round((task_completion + tool_success_rate) / 2.0, 2),
            latency_ms=round(latency_ms, 2),
            memory_delta_kb=0.0,
            tool_success_rate=round(tool_success_rate, 2),
            recovery_turns=recovery_turns,
            metrics_snapshot=metrics_snap,
            replay_hash=state_hash,
            evaluation_version=1,
        )
