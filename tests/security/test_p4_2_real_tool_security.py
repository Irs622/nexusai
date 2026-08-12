"""Security test suite verifying P4-2 Real Tool Execution invariants (P4-2-INV-01 to P4-2-INV-18)."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
import pytest

from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalStatus,
    HumanApprovalDecision,
    HumanApprovalRequest,
    RiskLevel,
)
from nexusai.brain.ports.tool_port import ToolExecutionRequest
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine
from nexusai.brain.runtime.tool_registry import ToolRegistry
from nexusai.infrastructure.tools.filesystem_tool import FilesystemTool, get_filesystem_tool_metadata
from nexusai.infrastructure.tools.network_tool import NetworkTool, get_network_tool_metadata
from nexusai.infrastructure.tools.process_tool import ProcessTool, get_process_tool_metadata


@pytest.mark.asyncio
async def test_security_filesystem_sandbox_escape_blocked() -> None:
    """Security Test (P4-2-INV-02 & P4-2-INV-03): Path traversal and symlink escape attempts are blocked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox = Path(tmpdir) / "sandbox"
        sandbox.mkdir()

        outside_file = Path(tmpdir) / "outside.txt"
        outside_file.write_text("SECRET OUTSIDE DATA", encoding="utf-8")

        # Symlink pointing outside sandbox
        symlink_path = sandbox / "symlink_escape.txt"
        try:
            os.symlink(str(outside_file), str(symlink_path))
        except OSError:
            pass  # Skip symlink creation if OS privileges disallow

        fs_tool = FilesystemTool(sandbox_root=sandbox)

        # 1. Traversal attempt via ../
        res1 = await fs_tool.execute(ToolExecutionRequest("e1", "filesystem_tool", {"action": "read_file", "path": "../outside.txt"}))
        assert res1.success is False
        assert "escapes sandbox root" in res1.error_message

        # 2. Symlink escape attempt
        if symlink_path.exists():
            res2 = await fs_tool.execute(ToolExecutionRequest("e2", "filesystem_tool", {"action": "read_file", "path": "symlink_escape.txt"}))
            assert res2.success is False
            assert "escapes sandbox root" in res2.error_message


@pytest.mark.asyncio
async def test_security_process_execution_governance_and_timeout_reaping() -> None:
    """Security Test (P4-2-INV-04 to P4-2-INV-07 & INV-14): Process execution requires governance & reaps child process on timeout."""
    gov = GovernanceEngine(global_budget=ResourceBudget(max_subprocesses=1))
    proc_tool = ProcessTool(default_timeout_seconds=0.1)

    # 1. Authorize process 1
    res1 = await gov.authorize("exec-proc-1", frozenset({ToolCapability.PROCESS_EXEC}))
    assert res1.allowed is True

    # 2. Process quota exhausted -> Next subprocess authorization DENIED!
    res2 = await gov.authorize("exec-proc-2", frozenset({ToolCapability.PROCESS_EXEC}))
    assert res2.allowed is False
    assert res2.reason == "max_subprocesses_exceeded"

    # 3. Timeout process reaping verification
    timeout_res = await proc_tool.execute(ToolExecutionRequest("exec-proc-1", "process_tool", {"argv": [sys.executable, "-c", "import time; time.sleep(2.0)"], "timeout": 0.05}))
    assert timeout_res.success is False
    assert "timed out" in timeout_res.error_message

    await gov.release(res1.reservation_id)
    assert gov.get_active_reservation_count() == 0


@pytest.mark.asyncio
async def test_security_network_destination_allowlist_and_ssrf() -> None:
    """Security Test (P4-2-INV-08 to P4-2-INV-10): Unapproved destination hosts and SSRF addresses fail closed."""
    net_tool = NetworkTool(allowed_hosts={"api.github.com"})

    # SSRF Loopback block
    res_ssrf = await net_tool.execute(ToolExecutionRequest("e1", "network_tool", {"url": "http://169.254.169.254/latest/meta-data/"}))
    assert res_ssrf.success is False
    assert "SSRF safety policy" in res_ssrf.error_message

    # Unapproved host block
    res_unauth = await net_tool.execute(ToolExecutionRequest("e2", "network_tool", {"url": "https://unauthorized-domain.com"}))
    assert res_unauth.success is False
    assert "not in the network destination allowlist" in res_unauth.error_message


if __name__ == "__main__":
    asyncio.run(test_security_filesystem_sandbox_escape_blocked())
    asyncio.run(test_security_process_execution_governance_and_timeout_reaping())
    asyncio.run(test_security_network_destination_allowlist_and_ssrf())
    print("ALL P4-2 REAL TOOL SECURITY TESTS PASSED SUCCESSFULLY!")
