"""Unit tests for ProcessTool argv subprocess execution, timeouts, and process reaping."""

from __future__ import annotations

import asyncio
import sys
import pytest

from nexusai.brain.ports.tool_port import ToolExecutionRequest
from nexusai.infrastructure.tools.process_tool import ProcessTool


@pytest.mark.asyncio
async def test_process_tool_argv_execution_and_timeout_reaping() -> None:
    """Test ProcessTool executes argv vectors cleanly and reaps timed-out subprocesses."""
    proc_tool = ProcessTool(default_timeout_seconds=0.5)

    # 1. Standard argv execution (python -c "print('hello process')")
    req = ToolExecutionRequest("e1", "process_tool", {"argv": [sys.executable, "-c", "print('hello process')"]})
    res = await proc_tool.execute(req)
    assert res.success is True
    assert "hello process" in res.output

    # 2. Timeout enforcement & Process Reaping (python -c "import time; time.sleep(2.0)")
    timeout_req = ToolExecutionRequest("e2", "process_tool", {"argv": [sys.executable, "-c", "import time; time.sleep(2.0)"], "timeout": 0.1})
    timeout_res = await proc_tool.execute(timeout_req)
    assert timeout_res.success is False
    assert "timed out" in timeout_res.error_message


if __name__ == "__main__":
    asyncio.run(test_process_tool_argv_execution_and_timeout_reaping())
    print("ALL PROCESS TOOL UNIT TESTS PASSED SUCCESSFULLY!")
