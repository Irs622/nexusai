"""Integration test suite for ProcessTool governed subprocess execution and real side-effects."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
import pytest

from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.ports.tool_port import ToolExecutionRequest
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.tool_registry import ToolRegistry
from nexusai.infrastructure.tools.process_tool import ProcessTool, get_process_tool_metadata


@pytest.mark.asyncio
async def test_process_integration_governed_real_execution() -> None:
    """Verify ProcessTool executes real Python subprocesses under governance and releases subprocess quotas cleanly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "work_script.py"
        script_path.write_text("import sys\nprint('Process execution completed successfully')\n", encoding="utf-8")

        proc_tool = ProcessTool(working_dir=tmpdir, default_timeout_seconds=5.0)
        registry = ToolRegistry()
        gov = GovernanceEngine(global_budget=ResourceBudget(max_subprocesses=5))

        await registry.register(get_process_tool_metadata())

        # 1. Validate & Authorize PROCESS_EXEC
        await registry.validate_tool("process_tool", requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}))
        res_gov = await gov.authorize("exec-proc-real", frozenset({ToolCapability.PROCESS_EXEC}))
        assert res_gov.allowed is True

        # 2. Perform actual subprocess execution
        req = ToolExecutionRequest("exec-proc-real", "process_tool", {"argv": [sys.executable, str(script_path)]})
        res = await proc_tool.execute(req)
        assert res.success is True
        assert "Process execution completed successfully" in res.output

        await gov.release(res_gov.reservation_id)
        assert gov.get_active_reservation_count() == 0


if __name__ == "__main__":
    asyncio.run(test_process_integration_governed_real_execution())
    print("ALL P4-2 PROCESS INTEGRATION TESTS PASSED SUCCESSFULLY!")
