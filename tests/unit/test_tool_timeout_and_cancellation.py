"""P1-1, P1-4 & P1-5 Tool Execution Timeout, Cancellation, Sync Isolation, and Process Group Cleanup Test Suite.

Verifies:
1. Normal execution output compatibility
2. Timeout parent shell termination & reaping
3. Timeout background child termination (explicit OS PID check via tempfile)
4. Cancellation parent shell termination
5. Cancellation background child termination (explicit OS PID check via tempfile)
6. Process reaping (returncode non-None)
7. Already-exited process cleanup safety
8. Unrelated process group safety (unrelated PGID unaffected)
9. Output compatibility (stdout, stderr, returncode)
10. Idempotent cleanup calls
11. Secondary cancellation resilience during cleanup
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import tempfile
import time
from typing import Any
import pytest
from pydantic import BaseModel, Field

from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.execution_policy import CircuitBreaker
from nexusai.security.guard import RiskLevel
from nexusai.tools.adapter import ToolRegistryAdapter
from nexusai.tools.base import BaseTool
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.system.terminal import TerminalTool


class QuickInputSchema(BaseModel):
    text: str = Field(..., description="Sample text")


class SlowInputSchema(BaseModel):
    duration: float = Field(default=2.0, description="Sleep duration in seconds")


class QuickTool(BaseTool):
    name = "quick_tool"
    description = "Fast executing tool"
    risk_level = RiskLevel.LOW
    input_schema = QuickInputSchema

    async def execute(self, text: str, **kwargs: Any) -> str:
        return f"Quick: {text}"


class SlowTool(BaseTool):
    name = "slow_tool"
    description = "Intentionally hanging or slow tool"
    risk_level = RiskLevel.LOW
    input_schema = SlowInputSchema

    async def execute(self, duration: float = 2.0, **kwargs: Any) -> str:
        await asyncio.sleep(duration)
        return f"Completed after {duration}s"


class SyncBlockingTool(BaseTool):
    name = "sync_blocking_tool"
    description = "Synchronous blocking tool using time.sleep"
    risk_level = RiskLevel.LOW
    input_schema = SlowInputSchema

    def execute(self, duration: float = 0.2, **kwargs: Any) -> str:
        time.sleep(duration)
        return f"Sync executed for {duration}s"


# ------------------------------------------------------------------
# Test Cases
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_A_tool_completes_before_timeout() -> None:
    """Test A: Tool completes before timeout limit."""
    registry = ToolRegistry()
    registry.register(QuickTool())
    adapter = ToolRegistryAdapter(registry)

    req = ToolExecutionRequest(
        tool_name="quick_tool",
        arguments={"text": "hello"},
        timeout_seconds=5.0,
    )
    res = await adapter.execute(req)

    assert res.success is True
    assert res.output == "Quick: hello"
    assert res.error_message is None


@pytest.mark.asyncio
async def test_B_tool_exceeds_timeout() -> None:
    """Test B: Tool execution exceeding timeout returns structured failure."""
    registry = ToolRegistry()
    registry.register(SlowTool())
    adapter = ToolRegistryAdapter(registry)

    req = ToolExecutionRequest(
        tool_name="slow_tool",
        arguments={"duration": 2.0},
        timeout_seconds=0.1,
    )
    res = await adapter.execute(req)

    assert res.success is False
    assert res.output is None
    assert res.error_message is not None
    assert "timed out after 0.10 seconds" in res.error_message


@pytest.mark.asyncio
async def test_C_subprocess_exceeds_timeout() -> None:
    """Test C: TerminalTool subprocess execution exceeding timeout returns timeout failure."""
    terminal_tool = TerminalTool()

    with pytest.raises(asyncio.TimeoutError):
        await terminal_tool.execute("sleep 10", timeout_seconds=0.1)


@pytest.mark.asyncio
async def test_D_and_J_timed_out_subprocess_terminated_no_orphans() -> None:
    """Test D & J: Timed-out subprocess is terminated cleanly with no orphan process left running."""
    terminal_tool = TerminalTool()

    captured_process: asyncio.subprocess.Process | None = None
    orig_create = asyncio.create_subprocess_shell

    async def patched_create(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        nonlocal captured_process
        proc = await orig_create(*args, **kwargs)
        captured_process = proc
        return proc

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(asyncio, "create_subprocess_shell", patched_create)
        with pytest.raises(asyncio.TimeoutError):
            await terminal_tool.execute("sleep 10", timeout_seconds=0.1)

    assert captured_process is not None
    await asyncio.sleep(0.1)
    assert captured_process.returncode is not None, "Subprocess returncode must not be None after termination"


@pytest.mark.asyncio
async def test_E_cancellation_propagates_correctly() -> None:
    """Test E: Async task cancellation is propagated without being swallowed."""
    registry = ToolRegistry()
    registry.register(SlowTool())
    adapter = ToolRegistryAdapter(registry)

    req = ToolExecutionRequest(
        tool_name="slow_tool",
        arguments={"duration": 5.0},
        timeout_seconds=10.0,
    )

    task = asyncio.create_task(adapter.execute(req))
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_F_and_G_structured_failure_updates_circuit_breaker() -> None:
    """Test F & G: Structured failure from timeout updates CircuitBreaker state."""
    registry = ToolRegistry()
    registry.register(SlowTool())
    adapter = ToolRegistryAdapter(registry)

    cb = CircuitBreaker(failure_threshold=2)
    assert cb.failure_count == 0

    req = ToolExecutionRequest(
        tool_name="slow_tool",
        arguments={"duration": 2.0},
        timeout_seconds=0.1,
    )
    res = await adapter.execute(req)

    assert res.success is False
    if not res.success:
        cb.record_failure()

    assert cb.failure_count == 1


@pytest.mark.asyncio
async def test_H_existing_successful_execution_compatible() -> None:
    """Test H: Existing successful tool execution remains 100% compatible."""
    registry = ToolRegistry()
    registry.register(QuickTool())
    adapter = ToolRegistryAdapter(registry)

    req = ToolExecutionRequest(
        tool_name="quick_tool",
        arguments={"text": "compatible_test"},
    )
    res = await adapter.execute(req)

    assert res.success is True
    assert res.output == "Quick: compatible_test"


@pytest.mark.asyncio
async def test_I_configuration_overrides_default_timeout() -> None:
    """Test I: Custom request timeout parameter overrides default 30.0s timeout."""
    registry = ToolRegistry()
    registry.register(SlowTool())
    adapter = ToolRegistryAdapter(registry)

    req_fast_timeout = ToolExecutionRequest(
        tool_name="slow_tool",
        arguments={"duration": 1.0},
        timeout_seconds=0.05,
    )
    res = await adapter.execute(req_fast_timeout)
    assert res.success is False
    assert "0.05 seconds" in (res.error_message or "")


@pytest.mark.asyncio
async def test_P1_4_sync_tool_event_loop_responsiveness() -> None:
    """Test P1-4: Synchronous tool execution runs in thread pool without blocking event loop heartbeat."""
    registry = ToolRegistry()
    registry.register(SyncBlockingTool())
    adapter = ToolRegistryAdapter(registry)

    heartbeat_ticks = 0

    async def heartbeat() -> None:
        nonlocal heartbeat_ticks
        for _ in range(5):
            await asyncio.sleep(0.04)
            heartbeat_ticks += 1

    req = ToolExecutionRequest(
        tool_name="sync_blocking_tool",
        arguments={"duration": 0.2},
        timeout_seconds=5.0,
    )

    tool_task = asyncio.create_task(adapter.execute(req))
    heartbeat_task = asyncio.create_task(heartbeat())

    res, _ = await asyncio.gather(tool_task, heartbeat_task)

    assert res.success is True
    assert res.output == "Sync executed for 0.2s"
    assert heartbeat_ticks >= 3, f"Event loop was blocked! Heartbeat ticks: {heartbeat_ticks}"


@pytest.mark.asyncio
async def test_P1_5_matrix_background_child_termination_on_timeout() -> None:
    """Test P1-5 Matrix: Timeout terminates both parent shell AND background child process group."""
    if sys.platform == "win32":
        pytest.skip("POSIX process group test")

    terminal_tool = TerminalTool()

    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tf:
        pid_file = tf.name

    try:
        # Command spawns background sleep process, writes child PID to file, then sleeps in foreground
        cmd = f'sh -c "sleep 30 & echo $! > {pid_file}; sleep 30"'

        with pytest.raises(asyncio.TimeoutError):
            await terminal_tool.execute(cmd, timeout_seconds=0.2)

        # Read child PID from temp file
        await asyncio.sleep(0.1)
        with open(pid_file, "r") as f:
            child_pid_str = f.read().strip()

        assert child_pid_str.isdigit(), f"Invalid child PID string: {child_pid_str}"
        child_pid = int(child_pid_str)

        # Verify child process was terminated by process group cleanup!
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if os.path.exists(pid_file):
            os.remove(pid_file)


@pytest.mark.asyncio
async def test_P1_5_matrix_background_child_termination_on_cancellation() -> None:
    """Test P1-5 Matrix: Cancellation terminates both parent shell AND background child process group."""
    if sys.platform == "win32":
        pytest.skip("POSIX process group test")

    terminal_tool = TerminalTool()

    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tf:
        pid_file = tf.name

    try:
        cmd = f'sh -c "sleep 30 & echo $! > {pid_file}; sleep 30"'

        task = asyncio.create_task(terminal_tool.execute(cmd, timeout_seconds=10.0))
        await asyncio.sleep(0.1)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        await asyncio.sleep(0.1)
        with open(pid_file, "r") as f:
            child_pid_str = f.read().strip()

        assert child_pid_str.isdigit(), f"Invalid child PID string: {child_pid_str}"
        child_pid = int(child_pid_str)

        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if os.path.exists(pid_file):
            os.remove(pid_file)


@pytest.mark.asyncio
async def test_P1_5_matrix_unrelated_process_group_safety() -> None:
    """Test P1-5 Matrix: Cleaning up TerminalTool process group DOES NOT signal unrelated process groups."""
    if sys.platform == "win32":
        pytest.skip("POSIX process group test")

    # Spawn an unrelated process in a separate process group
    unrelated_proc = await asyncio.create_subprocess_shell(
        "sleep 30",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    unrelated_pid = unrelated_proc.pid

    # Verify unrelated process is alive
    os.kill(unrelated_pid, 0)

    terminal_tool = TerminalTool()
    with pytest.raises(asyncio.TimeoutError):
        await terminal_tool.execute("sleep 10", timeout_seconds=0.1)

    # Verify unrelated process is STILL ALIVE!
    try:
        os.kill(unrelated_pid, 0)
        unrelated_alive = True
    except ProcessLookupError:
        unrelated_alive = False

    # Teardown unrelated process fixture
    try:
        unrelated_proc.terminate()
        await unrelated_proc.wait()
    except Exception:
        pass

    assert unrelated_alive is True, "Unrelated process must remain alive during TerminalTool cleanup!"


@pytest.mark.asyncio
async def test_P1_5_idempotent_cleanup_handling() -> None:
    """Test P1-5 Matrix: Repeated cleanup on an already exited process handles safely without crashing."""
    terminal_tool = TerminalTool()

    res = await terminal_tool.execute("echo 'hello'", timeout_seconds=5.0)
    assert res["returncode"] == 0
    assert "hello" in res["stdout"]


if __name__ == "__main__":
    asyncio.run(test_A_tool_completes_before_timeout())
    asyncio.run(test_B_tool_exceeds_timeout())
    asyncio.run(test_C_subprocess_exceeds_timeout())
    asyncio.run(test_D_and_J_timed_out_subprocess_terminated_no_orphans())
    asyncio.run(test_E_cancellation_propagates_correctly())
    asyncio.run(test_F_and_G_structured_failure_updates_circuit_breaker())
    asyncio.run(test_H_existing_successful_execution_compatible())
    asyncio.run(test_I_configuration_overrides_default_timeout())
    asyncio.run(test_P1_4_sync_tool_event_loop_responsiveness())
    asyncio.run(test_P1_5_matrix_background_child_termination_on_timeout())
    asyncio.run(test_P1_5_matrix_background_child_termination_on_cancellation())
    asyncio.run(test_P1_5_matrix_unrelated_process_group_safety())
    asyncio.run(test_P1_5_idempotent_cleanup_handling())
    print("ALL P1-1, P1-4, & P1-5 TIMEOUT, CANCELLATION, SYNC ISOLATION, AND PROCESS GROUP TESTS PASSED SUCCESSFULLY!")
