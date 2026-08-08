"""Unit tests for Phase 4 P1 Runtime Execution Replay (ReplayRecorder, ReplayRunner, ExecutionLog)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexusai.brain.replay.runner import ReplayRecorder, ReplayRunner
from nexusai.brain.replay.serialization import ExecutionLog


def test_execution_event_and_log_jsonl_serialization(tmp_path: Path):
    """Verify ExecutionEvent and ExecutionLog JSONL roundtrip serialization."""
    recorder = ReplayRecorder(session_id="session-xyz-100", goal_description="Replay test goal")

    recorder.record_turn(
        turn_index=1,
        step_title="Step 1 Title",
        tool_name="read_file",
        tool_arguments={"path": "/tmp/test.txt"},
        observation_payload="File payload content text",
        observation_success=True,
        compaction_triggered=False,
        summary_text="",
        decision="CONTINUE",
    )

    recorder.record_turn(
        turn_index=2,
        step_title="Step 2 Title",
        tool_name="write_file",
        tool_arguments={"path": "/tmp/out.txt"},
        observation_payload="Write success payload content",
        observation_success=True,
        compaction_triggered=True,
        summary_text="[Context Summary: 1 item compacted]",
        decision="COMPLETE",
    )

    log = recorder.build_log()
    assert len(log.events) == 2

    # Save to JSONL file
    jsonl_file = tmp_path / "replay_log.jsonl"
    log.save_jsonl(jsonl_file)

    assert jsonl_file.exists()

    # Load back from JSONL file
    loaded_log = ExecutionLog.load_jsonl(jsonl_file)

    assert loaded_log.session_id == "session-xyz-100"
    assert loaded_log.goal_description == "Replay test goal"
    assert len(loaded_log.events) == 2
    assert loaded_log.events[0].tool_name == "read_file"
    assert loaded_log.events[1].compaction_triggered is True


@pytest.mark.asyncio
async def test_replay_runner_deterministic_reproduction(tmp_path: Path):
    """Verify ReplayRunner replays pre-recorded ExecutionLog and reproduces deterministic WorkingMemory state."""
    recorder = ReplayRecorder(
        session_id="replay-session-200", goal_description="Deterministic goal"
    )

    recorder.record_turn(
        turn_index=1,
        step_title="Turn 1 Tool Read",
        tool_name="fetch_web",
        tool_arguments={"url": "https://example.com"},
        observation_payload="Recorded web page HTML content " * 10,
        observation_success=True,
        compaction_triggered=False,
        summary_text="",
        decision="COMPLETE",
    )

    log = recorder.build_log()
    jsonl_file = tmp_path / "deterministic_run.jsonl"
    log.save_jsonl(jsonl_file)

    runner = ReplayRunner()
    replayed_memory = await runner.replay_file(jsonl_file)

    assert replayed_memory.goal.description == "Deterministic goal"
    assert len(replayed_memory.observations) >= 1
    assert "Recorded web page HTML content" in str(replayed_memory.observations[0].payload)
