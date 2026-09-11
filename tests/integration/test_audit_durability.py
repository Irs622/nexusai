"""Integration test suite for durable append-only audit log with tamper evidence (Issue #33)."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import time

from fastapi.testclient import TestClient

from nexusai.api.server import create_app
from nexusai.brain.domain.audit import AuditEvent
from nexusai.infrastructure.persistence.sqlite_audit_store import SQLiteAuditStore
from nexusai.security.identity import Role


def test_audit_mutation_endpoints_disabled_in_prod_mode() -> None:
    """Requirement: POST /api/v1/audit/tamper & reset return 403 Forbidden when demo mode is disabled."""
    app = create_app(db_path=":memory:", studio_demo_mode=False)
    client = TestClient(app, headers={"X-NexusAI-API-Key": "nx_test_admin_key_123"})

    expected_msg = (
        "Audit log mutation endpoints are disabled in production mode. "
        "Set NEXUSAI_STUDIO_DEMO_MODE=true for demonstration environments."
    )

    # Test /tamper endpoint
    res_tamper = client.post(
        "/api/v1/audit/tamper",
        json={"tampered_field": "outcome", "new_value": "MALICIOUS"},
    )
    assert res_tamper.status_code == 403
    assert res_tamper.json()["detail"] == expected_msg

    # Test /reset endpoint
    res_reset = client.post("/api/v1/audit/reset")
    assert res_reset.status_code == 403
    assert res_reset.json()["detail"] == expected_msg


def test_audit_mutation_endpoints_allowed_in_demo_mode() -> None:
    """Requirement: When NEXUSAI_STUDIO_DEMO_MODE=true, tamper and reset operate on demo session."""
    app = create_app(db_path=":memory:", studio_demo_mode=True)
    client = TestClient(app, headers={"X-NexusAI-API-Key": "nx_test_admin_key_123"})

    # 1. Initial verify is valid
    v1 = client.get("/api/v1/audit/verify")
    assert v1.status_code == 200
    assert v1.json()["valid"] is True

    # 2. Tamper succeeds
    res_tamper = client.post(
        "/api/v1/audit/tamper",
        json={"tampered_field": "outcome", "new_value": "CORRUPTED_FOR_TEST"},
    )
    assert res_tamper.status_code == 200
    assert res_tamper.json()["status"] == "TAMPERED"

    # 3. Verification detects break
    v2 = client.get("/api/v1/audit/verify")
    assert v2.status_code == 200
    assert v2.json()["valid"] is False
    assert v2.json()["broken_at_sequence"] == 2

    # 4. Reset restores genesis
    res_reset = client.post("/api/v1/audit/reset")
    assert res_reset.status_code == 200
    assert res_reset.json()["status"] == "RESET_SUCCESS"

    v3 = client.get("/api/v1/audit/verify")
    assert v3.status_code == 200
    assert v3.json()["valid"] is True


def test_audit_process_restart_persistence_via_api() -> None:
    """Requirement: Audit events survive process restart (persisted to SQLite)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        # App Lifecycle 1: Trigger DAG execution and append audit events to persistent SQLite
        app1 = create_app(db_path=db_path, studio_demo_mode=False)
        with TestClient(app1, headers={"X-NexusAI-API-Key": "nx_test_admin_key_123"}) as client1:
            exec_res = client1.post(
                "/api/v1/dag/execute",
                json={"plan_id": "incident_response", "execution_id": "exec-durable-1"},
            )
            assert exec_res.status_code == 200
            # Allow async task to complete writing nodes
            time.sleep(1.2)

            events1 = client1.get("/api/v1/audit/events").json()
            assert len(events1) > 5

        # Terminate App 1
        del app1

        # App Lifecycle 2: Spin up a completely new App instance on same SQLite database
        app2 = create_app(db_path=db_path, studio_demo_mode=False)
        with TestClient(app2, headers={"X-NexusAI-API-Key": "nx_test_admin_key_123"}) as client2:
            # Events must survive process restart
            events2 = client2.get("/api/v1/audit/events").json()
            assert len(events2) == len(events1)
            assert events2[0]["id"] == events1[0]["id"]
            assert events2[-1]["id"] == events1[-1]["id"]

            # Entire persisted chain must verify cryptographically
            v_res = client2.get("/api/v1/audit/verify")
            assert v_res.status_code == 200
            v_data = v_res.json()
            assert v_data["valid"] is True
            assert v_data["hash_chain_valid"] is True
            assert v_data["sequence_valid"] is True
            assert v_data["event_count"] == len(events2)

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_tenant_scoped_audit_isolation_via_api() -> None:
    """Requirement: Cross-tenant audit access is forbidden at API layer unless admin/system."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        app = create_app(db_path=db_path, studio_demo_mode=False)
        api_key_service = app.state.api_key_service
        audit_store: SQLiteAuditStore = app.state.audit_store

        # Pre-populate distinct events for tenant-A and tenant-B
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            audit_store.append_event(
                AuditEvent(
                    event_id="ev-tenant-a-1",
                    event_type="TOOL_EXECUTION_COMPLETED",
                    session_id="s-a",
                    execution_id="exec-a",
                    plan_fingerprint="fp-a",
                    sequence_number=0,
                    tenant_id="tenant-A",
                    actor="user-alice",
                )
            )
        )
        loop.run_until_complete(
            audit_store.append_event(
                AuditEvent(
                    event_id="ev-tenant-b-1",
                    event_type="TOOL_EXECUTION_COMPLETED",
                    session_id="s-b",
                    execution_id="exec-b",
                    plan_fingerprint="fp-b",
                    sequence_number=0,
                    tenant_id="tenant-B",
                    actor="user-bob",
                )
            )
        )
        loop.close()

        # Register keys:
        # 1. Operator for Tenant-A
        api_key_service.register_raw_key(
            raw_key="key-tenant-a-op",
            tenant_id="tenant-A",
            user_id="alice",
            role=Role.OPERATOR,
        )
        # 2. Operator for Tenant-B
        api_key_service.register_raw_key(
            raw_key="key-tenant-b-op",
            tenant_id="tenant-B",
            user_id="bob",
            role=Role.OPERATOR,
        )
        # 3. System Admin
        api_key_service.register_raw_key(
            raw_key="key-sys-admin",
            tenant_id="admin-tenant",
            user_id="sysadmin",
            role=Role.ADMIN,
        )

        with TestClient(app) as client:
            # 1. Alice (tenant-A) querying without params gets only tenant-A events
            res_a = client.get(
                "/api/v1/audit/events", headers={"X-NexusAI-API-Key": "key-tenant-a-op"}
            )
            assert res_a.status_code == 200
            data_a = res_a.json()
            assert len(data_a) == 1
            assert data_a[0]["id"] == "ev-tenant-a-1"
            assert data_a[0]["tenant_id"] == "tenant-A"

            # 2. Alice trying to query tenant-B -> 403 Forbidden!
            res_a_leak = client.get(
                "/api/v1/audit/events?tenant_id=tenant-B",
                headers={"X-NexusAI-API-Key": "key-tenant-a-op"},
            )
            assert res_a_leak.status_code == 403
            assert "Cross-tenant audit query denied" in res_a_leak.json()["detail"]

            # 3. Admin can query tenant-B events successfully
            res_admin = client.get(
                "/api/v1/audit/events?tenant_id=tenant-B",
                headers={"X-NexusAI-API-Key": "key-sys-admin"},
            )
            assert res_admin.status_code == 200
            data_b = res_admin.json()
            assert len(data_b) == 1
            assert data_b[0]["id"] == "ev-tenant-b-1"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_actor_identity_population_from_auth() -> None:
    """Requirement: actor field populated from authenticated identity, never client body."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        app = create_app(db_path=db_path, studio_demo_mode=False)
        api_key_service = app.state.api_key_service

        api_key_service.register_raw_key(
            raw_key="key-alice-operator",
            tenant_id="default",
            user_id="alice-engineer",
            role=Role.ADMIN,  # Admin to execute DAG
        )

        with TestClient(app, headers={"X-NexusAI-API-Key": "key-alice-operator"}) as client:
            res = client.post(
                "/api/v1/dag/execute",
                json={
                    "plan_id": "incident_response",
                    "execution_id": "exec-actor-test",
                    "actor": "FAKE_CLIENT_ACTOR",  # Should be ignored
                },
            )
            assert res.status_code == 200
            time.sleep(1.2)

            events = client.get("/api/v1/audit/events").json()
            exec_events = [e for e in events if e.get("execution_id") == "exec-actor-test"]
            assert len(exec_events) > 0
            for ev in exec_events:
                assert ev["actor"] == "alice-engineer"
                assert ev["actor"] != "FAKE_CLIENT_ACTOR"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_startup_integrity_check_detects_compromised_database() -> None:
    """Requirement: Startup integrity check flags compromised audit chain on boot."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        # Pre-seed DB with corrupted event
        store = SQLiteAuditStore(db_path=db_path)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for i in range(1, 4):
            loop.run_until_complete(
                store.append_event(
                    AuditEvent(
                        event_id=f"boot-ev-{i}",
                        event_type="TOOL_EXECUTION_COMPLETED",
                        session_id="s1",
                        execution_id="e1",
                        plan_fingerprint="fp",
                        sequence_number=0,
                        tenant_id="default",
                    )
                )
            )
        loop.close()

        # Mutate SQLite directly to break integrity
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE audit_events SET outcome = 'TAMPERED_AT_REST' WHERE id = 'boot-ev-2'")
        conn.commit()
        conn.close()

        # Boot application with this database
        app = create_app(db_path=db_path, studio_demo_mode=False)
        with TestClient(app, headers={"X-NexusAI-API-Key": "nx_test_admin_key_123"}):
            # Lifespan startup runs integrity check
            assert getattr(app.state, "audit_compromised", False) is True

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
