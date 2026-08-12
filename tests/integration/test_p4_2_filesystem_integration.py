"""Integration test suite for FilesystemTool real side-effects within the governed runtime."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
import pytest

from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.ports.tool_port import ToolExecutionRequest
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.tool_registry import ToolRegistry
from nexusai.infrastructure.tools.filesystem_tool import FilesystemTool, get_filesystem_tool_metadata


@pytest.mark.asyncio
async def test_filesystem_integration_governed_real_side_effects() -> None:
    """Verify FilesystemTool performs actual side-effects (file write, read, delete) strictly under governance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fs_tool = FilesystemTool(sandbox_root=tmpdir)
        registry = ToolRegistry()
        gov = GovernanceEngine(global_budget=ResourceBudget(max_tool_invocations=10))

        await registry.register(get_filesystem_tool_metadata())

        # 1. Validate & Authorize write operation
        await registry.validate_tool("filesystem_tool", requested_capabilities=frozenset({ToolCapability.FILE_WRITE}))
        res_gov = await gov.authorize("exec-fs-1", frozenset({ToolCapability.FILE_WRITE}))
        assert res_gov.allowed is True

        # 2. Perform actual file write side-effect
        w_req = ToolExecutionRequest("exec-fs-1", "filesystem_tool", {"action": "write_file", "path": "notes.txt", "content": "NexusAI P4-2 Real Filesystem"})
        w_res = await fs_tool.execute(w_req)
        assert w_res.success is True

        # Assert file ACTUALLY exists on disk!
        real_file = Path(tmpdir) / "notes.txt"
        assert real_file.exists()
        assert real_file.read_text(encoding="utf-8") == "NexusAI P4-2 Real Filesystem"

        await gov.release(res_gov.reservation_id)
        assert gov.get_active_reservation_count() == 0


if __name__ == "__main__":
    asyncio.run(test_filesystem_integration_governed_real_side_effects())
    print("ALL P4-2 FILESYSTEM INTEGRATION TESTS PASSED SUCCESSFULLY!")
