"""Security test suite for P5-5 Tool Execution Sandbox & Isolation invariants (P5-5-INV-01 to P5-5-INV-25)."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.sandbox import IsolationPolicy, ResourceLimits, SandboxSpec
from nexusai.infrastructure.sandbox.capability_policy import CapabilityPolicyViolation
from nexusai.infrastructure.sandbox.grpc_sandbox_client import GRPCSandboxClient


@pytest.mark.asyncio
async def test_security_sandbox_denies_host_etc_passwd_access() -> None:
    """Security Test (P5-5-INV-08): Attempts to mount or read /etc/passwd MUST be DENIED by CapabilityPolicyEngine."""
    client = GRPCSandboxClient()

    spec = SandboxSpec(
        tool_id="process_tool",
        execution_id="exec-sec-sb-1",
        session_id="sess-sec-sb-1",
        fencing_token=1,
        arguments={"file": "/etc/passwd"},
        policy=IsolationPolicy(allowed_host_paths=["/etc/passwd"]),
    )

    res = await client.execute_in_sandbox(spec)
    assert res.success is False
    assert res.exit_code == 126
    assert "forbidden host path" in res.error_message.lower() or "denied" in res.error_message.lower()


@pytest.mark.asyncio
async def test_security_sandbox_denies_docker_socket_access() -> None:
    """Security Test (P5-5-INV-08 & P5-5-INV-17): Attempts to access /var/run/docker.sock MUST be DENIED!"""
    client = GRPCSandboxClient()

    spec = SandboxSpec(
        tool_id="process_tool",
        execution_id="exec-sec-sb-2",
        session_id="sess-sec-sb-2",
        fencing_token=1,
        arguments={"cmd": "cat /var/run/docker.sock"},
        policy=IsolationPolicy(allowed_host_paths=["/var/run/docker.sock"]),
    )

    res = await client.execute_in_sandbox(spec)
    assert res.success is False
    assert res.exit_code == 126


@pytest.mark.asyncio
async def test_security_sandbox_denies_host_postgres_and_vault_env_leakage() -> None:
    """Security Test (P5-5-INV-09 & P5-5-INV-10): Passing host DATABASE_URL or VAULT_TOKEN in ephemeral_env MUST be DENIED!"""
    client = GRPCSandboxClient()

    spec = SandboxSpec(
        tool_id="process_tool",
        execution_id="exec-sec-sb-3",
        session_id="sess-sec-sb-3",
        fencing_token=1,
        arguments={"cmd": "echo env"},
        ephemeral_env={"VAULT_TOKEN": "root-secret-token-123"},
    )

    res = await client.execute_in_sandbox(spec)
    assert res.success is False
    assert res.exit_code == 126
    assert "leaks host credentials" in res.error_message


@pytest.mark.asyncio
async def test_security_sandbox_execution_timeout_termination() -> None:
    """Security Test (P5-5-INV-20): Execution exceeding timeout limit is cleanly TERMINATED with exit_code == 124."""
    client = GRPCSandboxClient()

    spec = SandboxSpec(
        tool_id="process_tool",
        execution_id="exec-sec-sb-4",
        session_id="sess-sec-sb-4",
        fencing_token=1,
        arguments={"cmd": "sleep 10"},
        limits=ResourceLimits(timeout_seconds=0.01),
    )

    res = await client.execute_in_sandbox(spec)
    assert res.success is False
    assert res.exit_code == 124
    assert "timed out" in res.error_message


if __name__ == "__main__":
    asyncio.run(test_security_sandbox_denies_host_etc_passwd_access())
    asyncio.run(test_security_sandbox_denies_docker_socket_access())
    asyncio.run(test_security_sandbox_denies_host_postgres_and_vault_env_leakage())
    asyncio.run(test_security_sandbox_execution_timeout_termination())
    print("ALL P5-5 PROCESS ISOLATION SECURITY TESTS PASSED SUCCESSFULLY!")
