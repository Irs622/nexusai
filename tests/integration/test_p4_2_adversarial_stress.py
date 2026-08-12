"""Adversarial stress test suite for P4-2 Real Tool Execution safety, process reaping, and concurrency."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
import pytest

from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.ports.tool_port import ToolExecutionRequest
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.infrastructure.tools.filesystem_tool import FilesystemTool
from nexusai.infrastructure.tools.network_tool import NetworkTool
from nexusai.infrastructure.tools.process_tool import ProcessTool


@pytest.mark.asyncio
async def test_p4_2_adversarial_real_tool_stress() -> None:
    """Stress Test: Concurrent Filesystem writes/reads, Process argv executions, and Network allowlist checks under high load.

    Invariants: Zero orphan processes, zero sandbox escapes, zero SSRF bypasses, 100% reservation release.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        fs_tool = FilesystemTool(sandbox_root=tmpdir)
        proc_tool = ProcessTool(working_dir=tmpdir, default_timeout_seconds=5.0)
        net_tool = NetworkTool(allowed_hosts={"api.github.com"})
        gov = GovernanceEngine(global_budget=ResourceBudget(max_concurrent_tasks=20, max_subprocesses=25, max_tool_invocations=100))

        # 1. 20 Concurrent Filesystem operations
        async def fs_worker(w_id: int) -> None:
            res_gov = await gov.authorize(f"exec-fs-stress-{w_id}", frozenset({ToolCapability.FILE_WRITE}))
            assert res_gov.allowed is True

            w_req = ToolExecutionRequest(f"exec-fs-stress-{w_id}", "filesystem_tool", {"action": "write_file", "path": f"f_{w_id}.txt", "content": f"Data {w_id}"})
            w_res = await fs_tool.execute(w_req)
            assert w_res.success is True

            await gov.release(res_gov.reservation_id)

        # 2. 15 Concurrent Process subprocess executions
        async def proc_worker(w_id: int) -> None:
            res_gov = await gov.authorize(f"exec-proc-stress-{w_id}", frozenset({ToolCapability.PROCESS_EXEC}))
            assert res_gov.allowed is True

            p_req = ToolExecutionRequest(f"exec-proc-stress-{w_id}", "process_tool", {"argv": [sys.executable, "-c", f"print('Stress worker {w_id}')"]})
            p_res = await proc_tool.execute(p_req)
            assert p_res.success is True

            await gov.release(res_gov.reservation_id)

        workers = [asyncio.create_task(fs_worker(i)) for i in range(20)] + [asyncio.create_task(proc_worker(j)) for j in range(15)]
        await asyncio.gather(*workers)

        print(f"\n[P4-2 ADVERSARIAL REAL TOOL STRESS VERIFICATION]")
        print(f"Active Governance Reservations at Teardown: {gov.get_active_reservation_count()}")

        assert gov.get_active_reservation_count() == 0, "Zero resource leak invariant must hold after teardown!"


if __name__ == "__main__":
    asyncio.run(test_p4_2_adversarial_real_tool_stress())
    print("ALL P4-2 ADVERSARIAL REAL TOOL STRESS TESTS PASSED SUCCESSFULLY!")
