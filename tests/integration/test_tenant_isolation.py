"""Integration tests for multi-tenant isolation and RBAC boundary enforcement (Issue #31)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from nexusai.api.server import create_app
from nexusai.brain.domain.recovery import generate_idempotency_key
from nexusai.security.authentication import ApiKeyService
from nexusai.security.identity import Role


@pytest.fixture
def multi_tenant_app():
    """Create test application configured with multi-tenant API keys."""
    app = create_app(db_path=":memory:", studio_demo_mode=True)
    api_key_service: ApiKeyService = app.state.api_key_service

    # Register Tenant Alpha keys
    alpha_admin_key, _ = api_key_service.generate_key(
        tenant_id="tenant-alpha",
        user_id="alice-admin",
        role=Role.ADMIN,
        name="alpha-admin-key",
    )
    alpha_operator_key, _ = api_key_service.generate_key(
        tenant_id="tenant-alpha",
        user_id="bob-operator",
        role=Role.OPERATOR,
        name="alpha-operator-key",
    )

    # Register Tenant Beta keys
    beta_admin_key, _ = api_key_service.generate_key(
        tenant_id="tenant-beta",
        user_id="charlie-admin",
        role=Role.ADMIN,
        name="beta-admin-key",
    )
    beta_operator_key, _ = api_key_service.generate_key(
        tenant_id="tenant-beta",
        user_id="charlie-operator",
        role=Role.OPERATOR,
        name="beta-operator-key",
    )

    # Register Tenant Gamma keys (Viewer)
    gamma_viewer_key, _ = api_key_service.generate_key(
        tenant_id="tenant-gamma",
        user_id="dave-viewer",
        role=Role.VIEWER,
        name="gamma-viewer-key",
    )

    return {
        "app": app,
        "alpha_admin_key": alpha_admin_key,
        "alpha_operator_key": alpha_operator_key,
        "beta_admin_key": beta_admin_key,
        "beta_operator_key": beta_operator_key,
        "gamma_viewer_key": gamma_viewer_key,
    }


def test_tenant_audit_chain_isolation(multi_tenant_app: dict) -> None:
    """Verify Tenant Alpha audit tampering does not affect Tenant Beta's audit chain."""
    app = multi_tenant_app["app"]
    client_alpha = TestClient(
        app, headers={"X-NexusAI-API-Key": multi_tenant_app["alpha_admin_key"]}
    )
    client_beta = TestClient(app, headers={"X-NexusAI-API-Key": multi_tenant_app["beta_admin_key"]})

    # Initially both chains are valid
    assert client_alpha.post("/api/v1/audit/verify").json()["valid"] is True
    assert client_beta.post("/api/v1/audit/verify").json()["valid"] is True

    # Tamper Tenant Alpha's audit chain
    tamper_res = client_alpha.post(
        "/api/v1/audit/tamper",
        json={"tampered_field": "actor", "new_value": "rogue-actor"},
    )
    assert tamper_res.status_code == 200

    # Tenant Alpha's chain is now INVALID
    assert client_alpha.post("/api/v1/audit/verify").json()["valid"] is False

    # Tenant Beta's chain remains COMPLETELY VALID and unaffected
    assert client_beta.post("/api/v1/audit/verify").json()["valid"] is True

    # Resetting Alpha's chain restores Alpha without affecting Beta
    client_alpha.post("/api/v1/audit/reset")
    assert client_alpha.post("/api/v1/audit/verify").json()["valid"] is True
    assert client_beta.post("/api/v1/audit/verify").json()["valid"] is True


def test_tenant_pending_approvals_isolation(multi_tenant_app: dict) -> None:
    """Verify pending human approvals are strictly scoped to the requesting tenant."""
    app = multi_tenant_app["app"]
    client_alpha = TestClient(
        app, headers={"X-NexusAI-API-Key": multi_tenant_app["alpha_admin_key"]}
    )
    client_beta = TestClient(app, headers={"X-NexusAI-API-Key": multi_tenant_app["beta_admin_key"]})

    # Create a unique pending approval scoped exclusively to Tenant Alpha
    app.state.tenant_pending_approvals["tenant-alpha"] = [
        {
            "approval_id": "app-alpha-unique-999",
            "tool_id": "TerminalTool",
            "action_summary": "Alpha-only administrative action",
            "risk_level": "CRITICAL",
            "action_digest": "sha256:alpha999",
            "expires_at": 9999999999.0,
            "status": "PENDING",
            "command": "systemctl restart",
        }
    ]
    target_approval_id = "app-alpha-unique-999"

    # Verify Tenant Beta cannot see Alpha's approval
    beta_approvals = client_beta.get("/api/v1/governance/approvals").json()
    assert not any(a["approval_id"] == target_approval_id for a in beta_approvals)

    # Tenant Beta attempts to decide on Tenant Alpha's approval -> must return 404
    decision_payload = {"decision": "APPROVED", "actor": "charlie-admin"}
    cross_res = client_beta.post(
        f"/api/v1/governance/approvals/{target_approval_id}/decision",
        json=decision_payload,
    )
    assert cross_res.status_code == 404
    assert "not found" in cross_res.json()["detail"].lower()

    # Tenant Alpha can successfully decide on its own approval -> 200 OK
    alpha_res = client_alpha.post(
        f"/api/v1/governance/approvals/{target_approval_id}/decision",
        json=decision_payload,
    )
    assert alpha_res.status_code == 200
    assert alpha_res.json()["status"] == "APPROVED"


def test_tenant_governance_budget_isolation(multi_tenant_app: dict) -> None:
    """Verify governance resource budgets and limits are isolated per tenant."""
    app = multi_tenant_app["app"]
    client_alpha = TestClient(
        app, headers={"X-NexusAI-API-Key": multi_tenant_app["alpha_admin_key"]}
    )
    client_beta = TestClient(app, headers={"X-NexusAI-API-Key": multi_tenant_app["beta_admin_key"]})

    budget_alpha = client_alpha.get("/api/v1/governance/budget").json()
    budget_beta = client_beta.get("/api/v1/governance/budget").json()

    assert "limits" in budget_alpha
    assert "limits" in budget_beta
    assert "usage" in budget_alpha
    assert "usage" in budget_beta
    assert budget_alpha["limits"]["max_concurrent_tasks"] == 4
    assert budget_beta["limits"]["max_concurrent_tasks"] == 4


def test_rbac_viewer_endpoint_restrictions(multi_tenant_app: dict) -> None:
    """Verify viewer role is strictly restricted from mutating endpoints and tool executions."""
    app = multi_tenant_app["app"]
    client_viewer = TestClient(
        app, headers={"X-NexusAI-API-Key": multi_tenant_app["gamma_viewer_key"]}
    )

    # Allowed read-only endpoints
    assert client_viewer.get("/api/status").status_code == 200
    assert client_viewer.get("/api/tools").status_code == 200
    assert client_viewer.get("/api/v1/dag/plans").status_code == 200
    assert client_viewer.get("/api/v1/governance/budget").status_code == 200

    # Denied mutating endpoints (403 Forbidden)
    res_chat = client_viewer.post(
        "/api/chat",
        json={"prompt": "test prompt", "session_id": "test_s"},
    )
    assert res_chat.status_code == 403
    assert "RBAC access denied" in res_chat.json()["detail"]

    res_tool = client_viewer.post(
        "/api/tools/execute",
        json={"tool_name": "workspace_git_status", "arguments": {}},
    )
    assert res_tool.status_code == 403
    assert "RBAC access denied" in res_tool.json()["detail"]

    res_reset = client_viewer.post("/api/v1/audit/reset")
    assert res_reset.status_code == 403
    assert "RBAC access denied" in res_reset.json()["detail"]


def test_rbac_operator_tool_risk_boundary(multi_tenant_app: dict) -> None:
    """Verify operator role can execute LOW/MEDIUM risk tools, but is blocked on HIGH risk tools."""
    app = multi_tenant_app["app"]
    client_operator = TestClient(
        app, headers={"X-NexusAI-API-Key": multi_tenant_app["alpha_operator_key"]}
    )

    with patch("asyncio.create_subprocess_shell") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"On branch main", b"")
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        # 1. LOW risk tool execution -> 200 OK
        res_low = client_operator.post(
            "/api/tools/execute",
            json={"tool_name": "workspace_git_status", "arguments": {}},
        )
        assert res_low.status_code == 200
        assert res_low.json()["success"] is True

        # 2. HIGH risk tool execution -> 403 Forbidden (RBAC blocks operator)
        res_high = client_operator.post(
            "/api/tools/execute",
            json={"tool_name": "execute_terminal", "arguments": {"command": "whoami"}},
        )
        assert res_high.status_code == 403
        assert "RBAC access denied" in res_high.json()["detail"]


def test_tenant_scoped_idempotency_key_generation() -> None:
    """Verify idempotency keys are strictly scoped per tenant namespace."""
    # Tenant Alpha key
    key_alpha = generate_idempotency_key("exec-100", "node-A", 1, tenant_id="tenant-alpha")
    assert key_alpha == "tenant-alpha:exec-100-node-A:1"

    # Tenant Beta key
    key_beta = generate_idempotency_key("exec-100", "node-A", 1, tenant_id="tenant-beta")
    assert key_beta == "tenant-beta:exec-100-node-A:1"

    # Different namespaces
    assert key_alpha != key_beta

    # Default tenant namespace
    key_default = generate_idempotency_key("exec-100", "node-A", 1)
    assert key_default == "exec-100-node-A:1"


def test_audit_event_actor_and_metadata_tenant_binding(multi_tenant_app: dict) -> None:
    """Verify audit events record authenticated user identity and are tenant-isolated."""
    app = multi_tenant_app["app"]
    client_alpha = TestClient(
        app, headers={"X-NexusAI-API-Key": multi_tenant_app["alpha_admin_key"]}
    )
    client_beta = TestClient(app, headers={"X-NexusAI-API-Key": multi_tenant_app["beta_admin_key"]})

    # Retrieve initial audit events for Tenant Alpha
    res_alpha = client_alpha.get("/api/v1/audit/events")
    assert res_alpha.status_code == 200
    events_alpha = res_alpha.json()
    assert len(events_alpha) >= 5

    # Retrieve initial audit events for Tenant Beta
    res_beta = client_beta.get("/api/v1/audit/events")
    assert res_beta.status_code == 200
    events_beta = res_beta.json()
    assert len(events_beta) >= 5

    # Trigger DAG execution as Alice (Tenant Alpha)
    exec_res = client_alpha.post("/api/v1/dag/execute", json={"plan_id": "incident_response"})
    assert exec_res.status_code == 200
    assert exec_res.json()["status"] == "EXECUTION_STARTED"

    # Resetting Alpha's chain does not reset or alter Beta's chain
    client_alpha.post("/api/v1/audit/reset")
    post_reset_alpha = client_alpha.get("/api/v1/audit/events").json()
    post_reset_beta = client_beta.get("/api/v1/audit/events").json()

    assert len(post_reset_alpha) >= 1
    assert len(post_reset_beta) >= 5


def test_execution_inspection_cross_tenant_bola_blocked(multi_tenant_app: dict) -> None:
    """Verify Tenant Beta cannot inspect Tenant Alpha's execution records (NEX-SEC-001 BOLA)."""
    app = multi_tenant_app["app"]
    client_alpha = TestClient(
        app, headers={"X-NexusAI-API-Key": multi_tenant_app["alpha_operator_key"]}
    )
    client_beta_op = TestClient(
        app, headers={"X-NexusAI-API-Key": multi_tenant_app["beta_operator_key"]}
    )
    client_beta_admin = TestClient(
        app, headers={"X-NexusAI-API-Key": multi_tenant_app["beta_admin_key"]}
    )

    # 1. Trigger execution as Tenant Alpha
    exec_id = "exec-alpha-inspection-test"
    start_res = client_alpha.post(
        "/api/v1/dag/execute",
        json={"plan_id": "incident_response", "execution_id": exec_id},
    )
    assert start_res.status_code == 200

    # 2. Tenant Alpha inspects own execution -> 200 OK
    res_alpha = client_alpha.get(f"/api/v1/executions/{exec_id}")
    assert res_alpha.status_code == 200
    data_alpha = res_alpha.json()
    assert data_alpha["execution_id"] == exec_id
    assert data_alpha["tenant_id"] == "tenant-alpha"

    # 3. Tenant Beta (Operator) tries to inspect Tenant Alpha's execution -> 403 Forbidden (BOLA blocked!)
    res_beta = client_beta_op.get(f"/api/v1/executions/{exec_id}")
    assert res_beta.status_code == 403
    assert "Cross-tenant execution access denied" in res_beta.json()["detail"]

    # 4. Admin tries to inspect -> 200 OK (admin cross-tenant governance permitted)
    res_admin = client_beta_admin.get(f"/api/v1/executions/{exec_id}")
    assert res_admin.status_code == 200
    assert res_admin.json()["execution_id"] == exec_id

    # 5. Non-existent execution -> 404 Not Found
    res_404 = client_alpha.get("/api/v1/executions/exec-nonexistent")
    assert res_404.status_code == 404


def test_execution_cancellation_cross_tenant_bola_blocked(multi_tenant_app: dict) -> None:
    """Verify Tenant Beta cannot cancel Tenant Alpha's execution, and Viewer role cannot cancel (NEX-SEC-002)."""
    app = multi_tenant_app["app"]
    client_alpha = TestClient(
        app, headers={"X-NexusAI-API-Key": multi_tenant_app["alpha_operator_key"]}
    )
    client_beta_op = TestClient(
        app, headers={"X-NexusAI-API-Key": multi_tenant_app["beta_operator_key"]}
    )
    client_viewer = TestClient(
        app, headers={"X-NexusAI-API-Key": multi_tenant_app["gamma_viewer_key"]}
    )

    # 1. Trigger execution as Tenant Alpha
    exec_id = "exec-alpha-cancel-test"
    start_res = client_alpha.post(
        "/api/v1/dag/execute",
        json={"plan_id": "incident_response", "execution_id": exec_id},
    )
    assert start_res.status_code == 200

    # 2. Viewer role attempts cancellation -> 403 Forbidden
    res_viewer = client_viewer.post(
        f"/api/v1/executions/{exec_id}/cancel",
        params={"reason": "Unauthorized viewer attempt"},
    )
    assert res_viewer.status_code == 403
    assert "Viewer role cannot cancel executions" in res_viewer.json()["detail"]

    # 3. Tenant Beta (Operator) attempts cross-tenant cancellation -> 403 Forbidden
    res_cross = client_beta_op.post(
        f"/api/v1/executions/{exec_id}/cancel",
        params={"reason": "Malicious cross-tenant cancellation"},
    )
    assert res_cross.status_code == 403
    assert "Cross-tenant execution cancellation denied" in res_cross.json()["detail"]

    # 4. Verify execution was NOT cancelled by unauthorized requests
    check_res = client_alpha.get(f"/api/v1/executions/{exec_id}")
    assert check_res.status_code == 200
    assert check_res.json()["cancellation_requested"] is False

    # 5. Tenant Alpha cancels own execution -> 200 OK
    res_cancel = client_alpha.post(
        f"/api/v1/executions/{exec_id}/cancel",
        params={"reason": "Authorized cancellation"},
    )
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "CANCELLED"
    assert res_cancel.json()["cancelled"] is True


@pytest.mark.asyncio
async def test_sqlite_execution_store_tenant_isolation(tmp_path) -> None:
    """Verify SQLiteExecutionStateStore enforces tenant scoping at the database level."""
    from nexusai.brain.domain.execution_state import ExecutionRecord, ExecutionStatus
    from nexusai.infrastructure.persistence.sqlite_execution_store import SQLiteExecutionStateStore

    store = SQLiteExecutionStateStore(db_path=str(tmp_path / "exec_test.db"))
    exec_id = "exec-store-tenant-test"

    rec = ExecutionRecord(
        execution_id=exec_id,
        plan_id="plan-test",
        graph_hash="hash-test",
        status=ExecutionStatus.RUNNING,
        tenant_id="tenant-alpha",
        actor="alice",
    )
    await store.create_execution(rec)

    # 1. Loading with matching tenant returns record
    loaded_alpha = await store.load_execution(exec_id, tenant_id="tenant-alpha")
    assert loaded_alpha is not None
    assert loaded_alpha.execution_id == exec_id
    assert loaded_alpha.tenant_id == "tenant-alpha"

    # 2. Loading with mismatched tenant returns None (database-level containment)
    loaded_beta = await store.load_execution(exec_id, tenant_id="tenant-beta")
    assert loaded_beta is None

    # 3. Cancellation request with mismatched tenant returns False and does not mutate
    updated_beta = await store.mark_cancellation_requested(exec_id, tenant_id="tenant-beta")
    assert updated_beta is False
    assert await store.is_cancellation_requested(exec_id) is False

    # 4. Cancellation request with matching tenant succeeds and sets cancellation flag
    updated_alpha = await store.mark_cancellation_requested(exec_id, tenant_id="tenant-alpha")
    assert updated_alpha is True
    assert await store.is_cancellation_requested(exec_id) is True
