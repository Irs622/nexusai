"""Kubernetes manifest rendering and deployment validation integration test suite."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

import pytest
import yaml

HELM_DIR = "deploy/helm/nexusai"

requires_helm = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def _render(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["helm", "template", "r", HELM_DIR, "-n", "nx", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _docs(*args: str) -> list[dict[str, Any]]:
    result = _render(*args)
    assert result.returncode == 0, result.stderr
    return [d for d in yaml.safe_load_all(result.stdout) if d]


def _find(docs: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    return next(d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name)


def test_helm_chart_manifest_structure() -> None:
    """Integration Test: Verify Helm chart directory and manifest template files exist."""
    assert os.path.exists(os.path.join(HELM_DIR, "Chart.yaml"))
    assert os.path.exists(os.path.join(HELM_DIR, "values.yaml"))
    assert os.path.exists(os.path.join(HELM_DIR, "values-production.yaml"))
    assert os.path.exists(os.path.join(HELM_DIR, "templates/deployment-worker.yaml"))
    assert os.path.exists(os.path.join(HELM_DIR, "templates/networkpolicy.yaml"))
    assert os.path.exists(os.path.join(HELM_DIR, "templates/rbac.yaml"))
    assert os.path.exists(os.path.join(HELM_DIR, "templates/serviceaccount.yaml"))


@requires_helm
@pytest.mark.parametrize("values", [[], ["-f", f"{HELM_DIR}/values-production.yaml"]])
def test_control_plane_boots_on_read_only_root_filesystem(values: list[str]) -> None:
    """The control plane gets writable data/tmp/log mounts and the env bootstrap requires."""
    docs = _docs(*values)
    deploy = _find(docs, "Deployment", "nexusai-control-plane")
    container = deploy["spec"]["template"]["spec"]["containers"][0]

    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    mounts = {m["mountPath"] for m in container["volumeMounts"]}
    assert {"/data", "/tmp", "/app/logs"} <= mounts

    env = {e["name"]: e for e in container["env"]}
    assert len(env) == len(container["env"]), "duplicate env var names"
    assert env["NEXUSAI_EXECUTION_DB"]["value"] == "/data/execution.db"
    assert env["NEXUSAI_COORDINATOR_DB"]["value"] == "/data/coordinator.db"
    assert env["NEXUSAI_KEY_STORAGE_PATH"]["value"] == "/data/api_keys.json"
    assert env["NEXUSAI_ENV"]["value"] == "production"
    for secret_var in ("NEXUSAI_ADMIN_API_KEY", "NEXUSAI_APPROVAL_SECRET", "NEXUSAI_REDIS_URL"):
        assert "secretKeyRef" in env[secret_var]["valueFrom"]

    volumes = {v["name"]: v for v in deploy["spec"]["template"]["spec"]["volumes"]}
    assert volumes["data"]["persistentVolumeClaim"]["claimName"] == "r-data"
    assert _find(docs, "PersistentVolumeClaim", "r-data")
    assert _find(docs, "Service", "r-control-plane")["spec"]["ports"][0]["targetPort"] == "http"


@requires_helm
def test_env_override_does_not_duplicate_variables() -> None:
    docs = _docs("--set", "env.NEXUSAI_EXECUTION_DB=/x.db", "--set", "env.NEXUSAI_REDIS_URL=r")
    container = _find(docs, "Deployment", "nexusai-control-plane")["spec"]["template"]["spec"][
        "containers"
    ][0]
    names = [e["name"] for e in container["env"]]
    assert names.count("NEXUSAI_EXECUTION_DB") == 1
    assert names.count("NEXUSAI_REDIS_URL") == 1


@requires_helm
@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--set", "replicaCount.controlPlane=3"], "SQLite"),
        (["--set", "worker.enabled=true"], "worker.command"),
        (["--set", "sandbox.enabled=true"], "sandbox.command"),
    ],
)
def test_unsafe_configurations_fail_to_render(args: list[str], message: str) -> None:
    result = _render(*args)
    assert result.returncode != 0
    assert message in result.stderr


if __name__ == "__main__":
    test_helm_chart_manifest_structure()
    print("ALL HELM MANIFEST STRUCTURE INTEGRATION TESTS PASSED SUCCESSFULLY!")
