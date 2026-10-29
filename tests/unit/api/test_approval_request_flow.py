"""Tests for the pending approval flow: request -> supervisor decision -> bound token."""

from __future__ import annotations

from fastapi.testclient import TestClient

from nexusai.api.server import create_app
from nexusai.security.identity import Role

OPERATOR_KEY = "nx_key_operator_approval_flow_01"
SUPERVISOR_KEY = "nx_key_supervisor_approval_flow1"


def _clients() -> tuple[TestClient, TestClient, object]:
    app = create_app(db_path=":memory:")
    key_service = app.state.api_key_service
    key_service.register_raw_key(
        OPERATOR_KEY, tenant_id="default", user_id="operator-1", role=Role.OPERATOR
    )
    key_service.register_raw_key(
        SUPERVISOR_KEY, tenant_id="default", user_id="supervisor-1", role=Role.ADMIN
    )
    operator = TestClient(app, headers={"X-NexusAI-API-Key": OPERATOR_KEY})
    supervisor = TestClient(app, headers={"X-NexusAI-API-Key": SUPERVISOR_KEY})
    return operator, supervisor, app


def _request_approval(operator: TestClient) -> str:
    res = operator.post(
        "/api/v1/approvals/request",
        json={"tool_name": "execute_terminal", "arguments": {"command": "whoami"}},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "PENDING_REVIEW"
    return str(res.json()["approval_id"])


def test_supervisor_approval_issues_token_bound_to_requester() -> None:
    operator, supervisor, app = _clients()
    approval_id = _request_approval(operator)

    queue = supervisor.get("/api/v1/governance/approvals").json()
    assert any(item["approval_id"] == approval_id and item["status"] == "PENDING" for item in queue)

    decision = supervisor.post(
        f"/api/v1/governance/approvals/{approval_id}/decision",
        json={"decision": "APPROVED", "actor": "spoofed-name"},
    )
    assert decision.status_code == 200
    assert decision.json()["actor"] == "supervisor-1"
    assert decision.json()["token_issued"] is True

    # The token is never exposed in the shared queue, only to the requester.
    queue = supervisor.get("/api/v1/governance/approvals").json()
    assert all("approval_token" not in item for item in queue)
    assert "approval_token" not in supervisor.get(f"/api/v1/approvals/{approval_id}").json()

    token = operator.get(f"/api/v1/approvals/{approval_id}").json()["approval_token"]
    approval_service = app.state.security_guard.approval_service
    assert approval_service.validate_and_consume(
        token, "execute_terminal", {"command": "whoami"}, user_id="operator-1"
    )


def test_requester_cannot_approve_own_request() -> None:
    operator, _, _ = _clients()
    approval_id = _request_approval(operator)

    res = operator.post(
        f"/api/v1/governance/approvals/{approval_id}/decision", json={"decision": "APPROVED"}
    )
    assert res.status_code == 403


def test_invalid_decision_is_rejected() -> None:
    operator, supervisor, _ = _clients()
    approval_id = _request_approval(operator)

    res = supervisor.post(
        f"/api/v1/governance/approvals/{approval_id}/decision", json={"decision": "MAYBE"}
    )
    assert res.status_code == 400
