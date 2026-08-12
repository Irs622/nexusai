"""Reusable contract test suite for ISandboxExecutionPort implementations."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.sandbox import IsolationPolicy, ResourceLimits, SandboxSpec
from nexusai.brain.ports.sandbox_execution_port import ISandboxExecutionPort
from nexusai.infrastructure.sandbox.grpc_sandbox_client import GRPCSandboxClient


async def verify_sandbox_execution_contract(sandbox: ISandboxExecutionPort) -> None:
    """Verify any ISandboxExecutionPort adapter conforms to the domain contract."""
    spec = SandboxSpec(
        tool_id="process_tool",
        execution_id="exec-contract-sb",
        session_id="sess-contract-sb",
        fencing_token=1,
        arguments={"cmd": "echo hello"},
        limits=ResourceLimits(cpu_cores=1.0, memory_limit_mb=512, timeout_seconds=10.0),
        policy=IsolationPolicy(read_only_rootfs=True),
    )

    res = await sandbox.execute_in_sandbox(spec)
    assert res.execution_id == "exec-contract-sb"
    assert res.success is True
    assert res.exit_code == 0


@pytest.mark.asyncio
async def test_grpc_sandbox_client_conformance() -> None:
    """Test GRPCSandboxClient conformance to ISandboxExecutionPort contract."""
    client = GRPCSandboxClient()
    await verify_sandbox_execution_contract(client)


if __name__ == "__main__":
    asyncio.run(test_grpc_sandbox_client_conformance())
    print("ALL SANDBOX EXECUTION CONTRACT TESTS PASSED SUCCESSFULLY!")
