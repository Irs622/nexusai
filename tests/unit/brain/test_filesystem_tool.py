"""Unit tests for FilesystemTool canonical path sandbox boundary enforcement."""

from __future__ import annotations

import asyncio
import tempfile

import pytest

from nexusai.brain.ports.tool_port import ToolExecutionRequest
from nexusai.infrastructure.tools.filesystem_tool import FilesystemTool


@pytest.mark.asyncio
async def test_filesystem_tool_sandbox_boundary_and_operations() -> None:
    """Test FilesystemTool read, write, delete inside sandbox root, and path traversal rejection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fs = FilesystemTool(sandbox_root=tmpdir)

        # 1. Write file inside sandbox
        w_req = ToolExecutionRequest(
            tool_name="filesystem_tool",
            arguments={"action": "write_file", "path": "sub/test.txt", "content": "Hello Sandbox"},
            execution_id="e1",
        )
        w_res = await fs.execute(w_req)
        assert w_res.success is True

        # 2. Read file inside sandbox
        r_req = ToolExecutionRequest(
            tool_name="filesystem_tool",
            arguments={"action": "read_file", "path": "sub/test.txt"},
            execution_id="e2",
        )
        r_res = await fs.execute(r_req)
        assert r_res.success is True
        assert r_res.output == "Hello Sandbox"

        # 3. Path Traversal escape attempt -> MUST FAIL with PermissionError
        esc_req = ToolExecutionRequest(
            tool_name="filesystem_tool",
            arguments={"action": "read_file", "path": "../../etc/passwd"},
            execution_id="e3",
        )
        esc_res = await fs.execute(esc_req)
        assert esc_res.success is False
        assert "escapes sandbox root" in esc_res.error_message

        # 4. Delete file inside sandbox
        d_req = ToolExecutionRequest(
            tool_name="filesystem_tool",
            arguments={"action": "delete_file", "path": "sub/test.txt"},
            execution_id="e4",
        )
        d_res = await fs.execute(d_req)
        assert d_res.success is True


if __name__ == "__main__":
    asyncio.run(test_filesystem_tool_sandbox_boundary_and_operations())
    print("ALL FILESYSTEM TOOL UNIT TESTS PASSED SUCCESSFULLY!")
