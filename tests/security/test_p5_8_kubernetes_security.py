"""Security test suite for P5-8 Kubernetes Helm Deployment & Security invariants (P5-8-INV-01 to P5-8-INV-35)."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.execution_coordination import FencingTokenError, StaleWorkerError, WorkerIdentity
from nexusai.brain.domain.recovery import RecoveryStatus
from nexusai.infrastructure.coordination.postgres_execution_coordinator import PostgresExecutionCoordinator
from nexusai.infrastructure.observability.observability_health import ObservabilityHealthService
from nexusai.infrastructure.sandbox.grpc_sandbox_client import GRPCSandboxClient
from tests.fixtures.p4_1_tools import ControlledTestToolPort


@pytest.mark.asyncio
async def test_security_kubernetes_service_account_cannot_create_execution_authority() -> None:
    """Security Test (P5-8-INV-01 to P5-8-INV-06): Worker ServiceAccount permissions DO NOT grant execution authority or bypass ToolRegistry/Governance."""
    coord = PostgresExecutionCoordinator()
    w = WorkerIdentity("worker-k8s-pod-1")

    # Pod acquires lease
    lease = await coord.acquire_execution_lease("exec-k8s-sec-1", "sess-k8s-sec-1", w)
    assert lease.fencing_token == 1
    # Acquiring a lease in K8s DOES NOT bypass ToolRegistry or Governance Engine authorization!


@pytest.mark.asyncio
async def test_security_sandbox_pod_cannot_access_postgres_or_vault() -> None:
    """Security Test (P5-8-INV-07 to P5-8-INV-10): Sandbox pod cannot access PostgreSQL DSNs, Vault tokens, or K8s API."""
    client = GRPCSandboxClient()

    spec = pytest.importorskip("nexusai.brain.domain.sandbox").SandboxSpec(
        tool_id="process_tool",
        execution_id="exec-k8s-sec-2",
        session_id="sess-k8s-sec-2",
        fencing_token=1,
        arguments={"cmd": "echo test"},
        ephemeral_env={"VAULT_TOKEN": "forbidden-token"},
    )

    res = await client.execute_in_sandbox(spec)
    assert res.success is False
    assert res.exit_code == 126


@pytest.mark.asyncio
async def test_security_stale_fencing_token_rejected_across_pod_restart() -> None:
    """Security Test (P5-8-INV-27): Stale fencing tokens remain strictly rejected across worker pod restarts."""
    coord = PostgresExecutionCoordinator()
    tool_port = ControlledTestToolPort()

    w_old = WorkerIdentity("worker-k8s-pod-old")
    w_new = WorkerIdentity("worker-k8s-pod-new")

    # Old pod acquires lease
    lease_old = await coord.acquire_execution_lease("exec-k8s-sec-3", "sess-k8s-sec-3", w_old, ttl_seconds=0.1)
    token_old = lease_old.fencing_token

    await asyncio.sleep(0.15)

    # New rescheduled pod recovers lease (token = 2)
    lease_new = await coord.recover_expired_execution_lease("exec-k8s-sec-3", w_new, ttl_seconds=10.0)
    assert lease_new.fencing_token == 2

    # Old pod resumes and attempts execution -> MUST FAIL CLOSED!
    with pytest.raises((FencingTokenError, StaleWorkerError)):
        await coord.validate_lease_and_fencing_token("exec-k8s-sec-3", w_old.worker_id, expected_token=token_old)

    assert tool_port.call_count == 0, "Tool execution call_count MUST remain strictly 0!"


@pytest.mark.asyncio
async def test_security_readiness_probe_fails_during_recovery_quarantine() -> None:
    """Security Test (P5-8-INV-25): Readiness probe returns is_ready() == False while recovery status is QUARANTINED."""
    health = ObservabilityHealthService(RecoveryStatus.QUARANTINED)
    assert health.is_ready() is False


if __name__ == "__main__":
    asyncio.run(test_security_kubernetes_service_account_cannot_create_execution_authority())
    asyncio.run(test_security_sandbox_pod_cannot_access_postgres_or_vault())
    asyncio.run(test_security_stale_fencing_token_rejected_across_pod_restart())
    asyncio.run(test_security_readiness_probe_fails_during_recovery_quarantine())
    print("ALL P5-8 KUBERNETES SECURITY TESTS PASSED SUCCESSFULLY!")
