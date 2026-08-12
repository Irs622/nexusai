"""gRPC Sandbox Gateway end-to-end integration test suite for P5-5."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.sandbox import IsolationPolicy, ResourceLimits, SandboxSpec
from nexusai.infrastructure.sandbox.grpc_sandbox_client import GRPCSandboxClient


@pytest.mark.asyncio
async def test_grpc_sandbox_end_to_end_lifecycle() -> None:
    """Integration Test: Full lifecycle of a tool execution spec through gRPC Sandbox Gateway."""
    client = GRPCSandboxClient()

    spec = SandboxSpec(
        tool_id="filesystem_tool",
        execution_id="exec-grpc-e2e-1",
        session_id="sess-grpc-e2e-1",
        fencing_token=1,
        arguments={"action": "read", "path": "test.txt"},
        limits=ResourceLimits(cpu_cores=1.0, memory_limit_mb=256, timeout_seconds=5.0),
        policy=IsolationPolicy(read_only_rootfs=True, drop_all_capabilities=True),
    )

    res = await client.execute_in_sandbox(spec)
    assert res.execution_id == "exec-grpc-e2e-1"
    assert res.success is True
    assert res.exit_code == 0
    assert res.output["status"] == "completed"


if __name__ == "__main__":
    asyncio.run(test_grpc_sandbox_end_to_end_lifecycle())
    print("ALL GRPC SANDBOX INTEGRATION TESTS PASSED SUCCESSFULLY!")
