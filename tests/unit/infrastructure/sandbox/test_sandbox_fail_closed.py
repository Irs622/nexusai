"""Tests that the sandbox fails closed without a runtime and rejects unsafe host mounts."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexusai.brain.domain.sandbox import IsolationPolicy, ResourceLimits, SandboxSpec
from nexusai.infrastructure.sandbox import (
    CapabilityPolicyEngine,
    CapabilityPolicyViolation,
    ContainerRuntimeEngine,
)


def _spec(policy: IsolationPolicy | None = None) -> SandboxSpec:
    return SandboxSpec(
        "process_tool",
        "exec-fail-closed",
        "sess-fail-closed",
        1,
        {"cmd": "echo hi"},
        ResourceLimits(timeout_seconds=5.0),
        policy or IsolationPolicy(),
        {},
    )


@pytest.mark.asyncio
async def test_no_runtime_and_no_simulation_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUSAI_SANDBOX_OCI_ENABLED", raising=False)
    monkeypatch.delenv("NEXUSAI_SANDBOX_SIMULATION", raising=False)

    res = await ContainerRuntimeEngine().run(_spec())

    assert res.success is False
    assert res.exit_code == 126
    assert "No sandbox runtime available" in res.error_message


@pytest.mark.asyncio
async def test_simulation_results_are_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUSAI_SANDBOX_OCI_ENABLED", raising=False)
    monkeypatch.setenv("NEXUSAI_SANDBOX_SIMULATION", "true")

    res = await ContainerRuntimeEngine().run(_spec())

    assert res.success is True
    assert res.output["simulated"] is True


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/var/run",
        "/var/run/../run/docker.sock",
        "//var/run/docker.sock",
        "/etc",
        "relative/path",
        "/tmp/a:/etc:rw",
    ],
)
def test_unsafe_mount_paths_are_rejected(path: str) -> None:
    with pytest.raises(CapabilityPolicyViolation):
        CapabilityPolicyEngine.validate_spec(_spec(IsolationPolicy(allowed_host_paths=[path])))


def test_safe_mount_path_is_accepted(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    CapabilityPolicyEngine.validate_spec(_spec(IsolationPolicy(allowed_host_paths=[str(workdir)])))


def test_symlink_to_forbidden_path_is_rejected(tmp_path: Path) -> None:
    link = tmp_path / "sneaky"
    link.symlink_to("/etc")
    with pytest.raises(CapabilityPolicyViolation):
        CapabilityPolicyEngine.validate_spec(_spec(IsolationPolicy(allowed_host_paths=[str(link)])))
