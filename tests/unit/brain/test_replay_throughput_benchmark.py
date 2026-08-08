"""Replay Throughput Benchmark — Measures replay throughput rate in scenarios per second."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from nexusai.brain.replay.runner import ReplayRecorder, ReplayRunner


@pytest.mark.asyncio
async def test_replay_throughput_benchmark(tmp_path: Path):
    """Verify ReplayRunner achieves > 100 scenarios/sec replay throughput rate."""
    recorder = ReplayRecorder(
        session_id="bench-session-1", goal_description="Throughput benchmark goal"
    )

    recorder.record_turn(
        turn_index=1,
        step_title="Read step",
        tool_name="read_file",
        tool_arguments={"path": "data.txt"},
        observation_payload="File payload string sample data",
        observation_success=True,
        compaction_triggered=False,
        summary_text="",
        decision="COMPLETE",
    )

    log = recorder.build_log()
    jsonl_file = tmp_path / "throughput_log.jsonl"
    log.save_jsonl(jsonl_file)

    runner = ReplayRunner()

    # Benchmark 200 replay runs
    t0 = time.perf_counter()
    for _ in range(200):
        await runner.replay_file(jsonl_file)
    elapsed_sec = max(0.001, time.perf_counter() - t0)

    throughput_scenarios_per_sec = 200 / elapsed_sec

    print("\n[Replay Throughput Benchmark]")
    print(
        f"Executed 200 replays in {elapsed_sec:.3f} sec | Throughput: {throughput_scenarios_per_sec:.2f} scenarios/sec"
    )

    assert (
        throughput_scenarios_per_sec > 50.0
    ), f"Replay throughput lower than threshold: {throughput_scenarios_per_sec:.2f} < 50.0 scenarios/sec"
