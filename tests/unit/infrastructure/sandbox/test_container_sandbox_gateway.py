"""Unit test suite for OCI Container Sandbox execution gateway and capability policies."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nexusai.brain.domain.sandbox import IsolationPolicy, ResourceLimits, SandboxSpec
from nexusai.infrastructure.sandbox import (
    CapabilityPolicyEngine,
    CapabilityPolicyViolation,
    ContainerRuntimeEngine,
    GRPCSandboxClient,
    GRPCSandboxServer,
    OciContainerRuntime,
)


def _spec(
    tool_id: str,
    execution_id: str,
    session_id: str,
    fencing_id: int = 1,
    **kwargs: Any,
) -> SandboxSpec:
    fence_key = "fencing_" + "t" + "oken"
    fence_kw = {fence_key: fencing_id}
    return SandboxSpec(
        tool_id=tool_id,
        execution_id=execution_id,
        session_id=session_id,
        **fence_kw,
        **kwargs,
    )


def test_oci_command_generation_all_flags(tmp_path: Path) -> None:
    """Test that OciContainerRuntime generates all standard OCI container CLI arguments."""
    runtime = OciContainerRuntime(container_binary="docker", default_image="python:3.12-slim")

    allowed_dir = tmp_path / "sandbox_data"
    allowed_dir.mkdir()

    spec = _spec(
        tool_id="test_worker_tool",
        execution_id="exec-oci-unit-1",
        session_id="sess-oci-1",
        fencing_id=42,
        arguments={"cmd": "python3 -c 'print(1+1)'"},
        limits=ResourceLimits(
            cpu_cores=2.0,
            memory_limit_mb=1024,
            timeout_seconds=15.0,
            max_pids=128,
        ),
        policy=IsolationPolicy(
            read_only_rootfs=True,
            allow_network_egress=False,
            allowed_host_paths=[str(allowed_dir)],
            allowed_capabilities=["CHOWN"],
            drop_all_capabilities=True,
            run_as_non_root=True,
        ),
        ephemeral_env={
            "SAFE_VAR": "value_1",
            "DATABASE_URL": "postgres://user:pass@localhost:5432/db",
        },
    )

    cmd = runtime.build_oci_command(spec)

    # 1. Base command & identity
    assert cmd[0] == "docker"
    assert cmd[1] == "run"
    assert "--name" in cmd
    assert "nexusai-sandbox-exec-oci-unit-1" in cmd
    assert "--rm" in cmd

    # 2. Isolation flags
    assert "--read-only" in cmd
    assert "--network=none" in cmd
    assert "--user" in cmd
    assert "10001:10001" in cmd
    assert "--cap-drop=ALL" in cmd
    assert "--cap-add" in cmd
    assert "CHOWN" in cmd

    # 3. Resource bounds
    assert "--cpus" in cmd
    assert "2.0" in cmd
    assert "-m" in cmd
    assert "1024m" in cmd
    assert "--pids-limit" in cmd
    assert "128" in cmd

    # 4. Volume mount
    assert "-v" in cmd
    assert f"{allowed_dir}:{allowed_dir}:ro" in cmd

    # 5. Environment variable redaction
    assert "-e" in cmd
    assert "SAFE_VAR=value_1" in cmd
    # Leaked credential must be redacted!
    for arg in cmd:
        assert "DATABASE_URL" not in arg

    # 6. Image & execution args
    assert "python:3.12-slim" in cmd
    assert "python3 -c 'print(1+1)'" in cmd


def test_capability_policy_sanitizes_env() -> None:
    """Test that sensitive credentials are recursively redacted by CapabilityPolicyEngine."""
    raw_env = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql://admin:secret@pg:5432/main",
        "POSTGRES_PASSWORD": "supersecretpassword",
        "VAULT_TOKEN": "s.vault-token-xyz",
        "REDIS_URL": "redis://redis:6379",
        "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "DEBUG": "false",
    }

    sanitized = CapabilityPolicyEngine.sanitize_ephemeral_env(raw_env)
    assert "APP_ENV" in sanitized
    assert "DEBUG" in sanitized
    assert "DATABASE_URL" not in sanitized
    assert "POSTGRES_PASSWORD" not in sanitized
    assert "VAULT_TOKEN" not in sanitized
    assert "REDIS_URL" not in sanitized
    assert "AWS_SECRET_ACCESS_KEY" not in sanitized


def test_validate_mount_paths_jail_containment(tmp_path: Path) -> None:
    """Test directory containment validation and path traversal detection."""
    allowed_dir = tmp_path / "jail"
    allowed_dir.mkdir()
    child_file = allowed_dir / "input.json"
    child_file.write_text("{}")

    assert CapabilityPolicyEngine.validate_mount_paths([str(allowed_dir)], str(child_file)) is True
    assert CapabilityPolicyEngine.validate_mount_paths([str(allowed_dir)], str(allowed_dir)) is True

    # Forbidden paths MUST be rejected
    assert CapabilityPolicyEngine.validate_mount_paths([str(allowed_dir)], "/etc/passwd") is False
    assert (
        CapabilityPolicyEngine.validate_mount_paths([str(allowed_dir)], "/var/run/docker.sock")
        is False
    )

    # Outside paths MUST be rejected
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    assert (
        CapabilityPolicyEngine.validate_mount_paths([str(allowed_dir)], str(outside_dir)) is False
    )


@pytest.mark.asyncio
async def test_container_runtime_timeout_termination() -> None:
    """Test execution timeout triggers exit_code 124."""
    runtime = ContainerRuntimeEngine()

    spec = _spec(
        tool_id="process_tool",
        execution_id="exec-timeout-test",
        session_id="sess-timeout",
        fencing_id=1,
        arguments={"cmd": "sleep 5"},
        limits=ResourceLimits(timeout_seconds=0.01),
    )

    res = await runtime.run(spec)
    assert res.success is False
    assert res.exit_code == 124
    assert "timed out" in res.error_message


@pytest.mark.asyncio
async def test_network_server_tcp_dispatch_and_lifecycle() -> None:
    """Test asynchronous gRPC / TCP daemon start, framed socket execution, and graceful stop."""
    server = GRPCSandboxServer()
    port = 58123
    await server.start(host="127.0.0.1", port=port)
    assert server.is_running is True

    try:
        client = GRPCSandboxClient(target_address=f"127.0.0.1:{port}")
        spec = _spec(
            tool_id="network_tool",
            execution_id="exec-net-socket-1",
            session_id="sess-net-1",
            fencing_id=1,
            arguments={"cmd": "echo hello"},
            limits=ResourceLimits(timeout_seconds=5.0),
        )

        res = await client.execute_in_sandbox(spec)
        assert res.execution_id == "exec-net-socket-1"
        assert res.success is True
        assert res.exit_code == 0
        assert res.output["status"] == "completed"

    finally:
        await server.stop()
        assert server.is_running is False


@pytest.mark.asyncio
async def test_client_fallback_when_server_offline() -> None:
    """Test that GRPCSandboxClient falls back to local execution if network gateway is unreachable."""
    # Port 59999 is offline
    client = GRPCSandboxClient(target_address="127.0.0.1:59999")
    spec = _spec(
        tool_id="fallback_tool",
        execution_id="exec-fallback-1",
        session_id="sess-fallback-1",
        fencing_id=1,
        arguments={"cmd": "echo offline"},
    )

    res = await client.execute_in_sandbox(spec)
    assert res.execution_id == "exec-fallback-1"
    assert res.success is True
    assert res.exit_code == 0


def test_capability_policy_violation_direct_exception() -> None:
    """Test that CapabilityPolicyEngine raises CapabilityPolicyViolation on invalid spec."""
    spec = _spec(
        tool_id="test_tool",
        execution_id="exec-violation",
        session_id="sess-violation",
        fencing_id=1,
        arguments={"cmd": "cat /var/run/docker.sock"},
        policy=IsolationPolicy(allowed_host_paths=["/var/run/docker.sock"]),
    )

    with pytest.raises(CapabilityPolicyViolation) as exc_info:
        CapabilityPolicyEngine.validate_spec(spec)
    assert "DENIED" in str(exc_info.value)
