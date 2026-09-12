"""Unit test suite for NexusAI Studio API endpoints (Issue #24)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexusai.api.server import create_app


@pytest.fixture
def studio_client() -> TestClient:
    """Fixture providing isolated TestClient instance in demo mode."""
    app = create_app(db_path=":memory:", studio_demo_mode=True)
    return TestClient(app, headers={"X-NexusAI-API-Key": "nx_test_admin_key_123"})


def test_studio_dag_plans_listing(studio_client: TestClient) -> None:
    """Test listing available DAG plan templates."""
    response = studio_client.get("/api/v1/dag/plans")
    assert response.status_code == 200
    assert response.headers.get("X-NexusAI-Mode") == "simulation"
    plans = response.json()
    assert isinstance(plans, list)
    assert len(plans) >= 3

    plan_ids = [p["plan_id"] for p in plans]
    assert "incident_response" in plan_ids
    assert "vulnerability_audit" in plan_ids
    assert "data_pipeline" in plan_ids

    for p in plans:
        assert "title" in p
        assert "description" in p
        assert p["nodes_count"] > 0
        assert p["edges_count"] > 0


def test_studio_dag_current_plan(studio_client: TestClient) -> None:
    """Test retrieving full PlanGraph structure for a specified plan."""
    response = studio_client.get("/api/v1/dag/current?plan_id=incident_response")
    assert response.status_code == 200
    assert response.headers.get("X-NexusAI-Mode") == "simulation"
    data = response.json()
    assert data["plan_id"] == "incident_response"
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 6
    assert len(data["edges"]) == 6


def test_studio_dag_current_plan_not_found(studio_client: TestClient) -> None:
    """Test 404 response on non-existent plan ID."""
    response = studio_client.get("/api/v1/dag/current?plan_id=non_existent_plan")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_studio_dag_execute_endpoint(studio_client: TestClient) -> None:
    """Test triggering asynchronous DAG execution and alias route."""
    # Test primary endpoint
    res1 = studio_client.post(
        "/api/v1/dag/execute",
        json={"plan_id": "incident_response"},
    )
    assert res1.status_code == 200
    assert res1.headers.get("X-NexusAI-Mode") == "simulation"
    data1 = res1.json()
    assert data1["status"] == "EXECUTION_STARTED"
    assert data1["plan_id"] == "incident_response"
    assert "execution_id" in data1
    assert data1["nodes_count"] == 6

    # Test alias endpoint (/api/v1/execute)
    res2 = studio_client.post(
        "/api/v1/execute",
        json={"plan_id": "vulnerability_audit"},
    )
    assert res2.status_code == 200
    assert res2.headers.get("X-NexusAI-Mode") == "simulation"
    data2 = res2.json()
    assert data2["status"] == "EXECUTION_STARTED"
    assert data2["plan_id"] == "vulnerability_audit"


def test_studio_audit_events_endpoint(studio_client: TestClient) -> None:
    """Test retrieving cryptographic audit chain records."""
    response = studio_client.get("/api/v1/audit/events")
    assert response.status_code == 200
    assert response.headers.get("X-NexusAI-Mode") == "simulation"
    events = response.json()
    assert isinstance(events, list)
    assert len(events) >= 5

    # First event must originate from GENESIS_HASH
    genesis = "0" * 64
    assert events[0]["previous_event_hash"] == genesis
    assert events[0]["sequence_number"] == 1
    assert len(events[0]["event_hash"]) == 64

    # Subsequent events must form cryptographic link
    for i in range(1, len(events)):
        assert events[i]["previous_event_hash"] == events[i - 1]["event_hash"]
        assert events[i]["sequence_number"] == i + 1


def test_studio_audit_verify_intact_chain(studio_client: TestClient) -> None:
    """Test that initial undisturbed audit chain verifies with zero violations."""
    response = studio_client.post("/api/v1/audit/verify")
    assert response.status_code == 200
    assert response.headers.get("X-NexusAI-Mode") == "simulation"
    data = response.json()
    assert data["valid"] is True
    assert data["hash_chain_valid"] is True
    assert data["sequence_valid"] is True
    assert data["violations"] == []
    assert data["event_count"] >= 5


def test_studio_audit_tamper_and_detection(studio_client: TestClient) -> None:
    """Test that malicious mutation in audit event triggers immediate cryptographic detection."""
    # 1. Verify chain is initially valid
    init_res = studio_client.post("/api/v1/audit/verify")
    assert init_res.json()["valid"] is True

    # 2. Inject tampering mutation
    tamper_res = studio_client.post(
        "/api/v1/audit/tamper",
        json={
            "tampered_field": "outcome",
            "new_value": "MALICIOUS_TAMPERED_OUTCOME",
        },
    )
    assert tamper_res.status_code == 200
    assert tamper_res.headers.get("X-NexusAI-Mode") == "simulation"
    tamper_data = tamper_res.json()
    assert tamper_data["status"] == "TAMPERED"

    # 3. Verification must now FAIL with exact violation details
    verify_res = studio_client.post("/api/v1/audit/verify")
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    assert verify_data["valid"] is False
    assert verify_data["hash_chain_valid"] is False
    assert len(verify_data["violations"]) > 0
    assert any("Tampered payload" in v for v in verify_data["violations"])


def test_studio_audit_reset(studio_client: TestClient) -> None:
    """Test that resetting audit chain clears violations and restores cryptographic validity."""
    # Tamper first
    studio_client.post(
        "/api/v1/audit/tamper",
        json={"tampered_field": "actor", "new_value": "rogue-agent"},
    )
    assert studio_client.post("/api/v1/audit/verify").json()["valid"] is False

    # Reset
    reset_res = studio_client.post("/api/v1/audit/reset")
    assert reset_res.status_code == 200
    assert reset_res.headers.get("X-NexusAI-Mode") == "simulation"
    assert reset_res.json()["status"] == "RESET_SUCCESS"

    # Must verify clean again
    verify_res = studio_client.post("/api/v1/audit/verify")
    assert verify_res.json()["valid"] is True
    assert verify_res.json()["violations"] == []


def test_studio_governance_budget_endpoint(studio_client: TestClient) -> None:
    """Test retrieving resource quota limits and current usage metrics."""
    response = studio_client.get("/api/v1/governance/budget")
    assert response.status_code == 200
    assert response.headers.get("X-NexusAI-Mode") == "simulation"
    budget = response.json()
    assert "limits" in budget
    assert "usage" in budget
    assert "percentages" in budget
    assert budget["limits"]["max_concurrent_tasks"] == 4
    assert budget["limits"]["max_memory_mb"] == 512
    assert budget["usage"]["memory_mb_used"] > 0


def test_studio_governance_approvals_and_decision(studio_client: TestClient) -> None:
    """Test listing pending approvals, submitting operator decisions, and receiving grants."""
    # List pending
    list_res = studio_client.get("/api/v1/governance/approvals")
    assert list_res.status_code == 200
    assert list_res.headers.get("X-NexusAI-Mode") == "simulation"
    approvals = list_res.json()
    assert len(approvals) >= 2
    app_id = approvals[0]["approval_id"]

    # Approve decision
    approve_res = studio_client.post(
        f"/api/v1/governance/approvals/{app_id}/decision",
        json={"decision": "APPROVED", "actor": "lead-sec-operator"},
    )
    assert approve_res.status_code == 200
    assert approve_res.headers.get("X-NexusAI-Mode") == "simulation"
    data = approve_res.json()
    assert data["status"] == "APPROVED"
    assert data["grant_id"].startswith("grant-")

    # Second submission on already resolved approval must return 400
    dup_res = studio_client.post(
        f"/api/v1/governance/approvals/{app_id}/decision",
        json={"decision": "APPROVED"},
    )
    assert dup_res.status_code == 400

    # Deny decision on 2nd item
    app_id2 = approvals[1]["approval_id"]
    deny_res = studio_client.post(
        f"/api/v1/governance/approvals/{app_id2}/decision",
        json={"decision": "DENIED", "actor": "lead-sec-operator"},
    )
    assert deny_res.status_code == 200
    assert deny_res.json()["status"] == "DENIED"


@pytest.mark.asyncio
async def test_studio_sse_endpoint_handshake(studio_client: TestClient) -> None:
    """Test SSE event stream endpoint connection and handshake."""
    routes: list[Any] = list(getattr(studio_client.app, "routes", []))
    found = 0
    for route in routes:
        if getattr(route, "path", None) in ("/api/events/stream", "/events"):
            resp = await route.endpoint()
            assert resp.media_type == "text/event-stream"
            first_event = await anext(resp.body_iterator)
            assert "event: handshake" in first_event
            assert "CONNECTED" in first_event
            found += 1

    assert found >= 2


def test_studio_ui_demo_mode_banner_present(studio_client: TestClient) -> None:
    """Test that web/index.html includes the prominent [DEMO MODE — Simulated Execution] banner (Issue #29)."""
    response = studio_client.get("/")
    assert response.status_code == 200
    html_content = response.text
    assert "[DEMO MODE — Simulated Execution]" in html_content
    assert "dag-demo-banner" in html_content
    assert "SIMULATION" in html_content
