"""Unit and integration tests for Execution API Idempotency.

Tests cover:
- In-memory and SQLite storage engines
- Identity scoping (tenant_id + user_id + idempotency_key)
- Payload fingerprinting and 409 Conflict on payload mismatch
- Execution lifecycle state machine (PENDING, RUNNING, SUCCEEDED, FAILED_TRANSIENT, FAILED_TERMINAL, CANCELLED, EXPIRED)
- Atomicity under concurrent duplicate requests
- Transient failure retry vs terminal failure replay
- TTL expiration and key reuse
- Cross-tenant isolation
- Response cache secret sanitization
- CQRS CommandBus layer idempotency
- DAG execution engine layer idempotency
- HTTP endpoints: POST /api/tools/execute and POST /api/v1/dag/execute
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from nexusai.api.server import create_app
from nexusai.brain.domain.agent import (
    AgentGoal,
    PlanningConstraints,
    PlanningContext,
    PlanningGoal,
)
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import (
    IToolPort,
    ToolExecutionRequest,
    ToolExecutionResult,
)
from nexusai.bus.bus import EventBus
from nexusai.bus.commands import ExecuteToolCommand, ExecuteToolCommandHandler
from nexusai.core.config import SystemConfig
from nexusai.core.errors import (
    IdempotencyConflictError,
    IdempotencyPayloadMismatchError,
)
from nexusai.infrastructure.idempotency import (
    IdempotencyState,
    InMemoryIdempotencyStore,
    SqliteIdempotencyStore,
    compute_payload_fingerprint,
)
from nexusai.security.guard import RiskLevel, SecurityGuard
from nexusai.tools.base import BaseTool


# --- Mock Tools & Fixtures ---
class DummyArgs(BaseModel):
    command: str = Field(default="echo")
    delay: float = Field(default=0.0)
    should_fail: bool = Field(default=False)
    fail_transient: bool = Field(default=False)
    secret_key: str = Field(default="")


class MockEchoTool(BaseTool):
    name: str = "mock_echo_tool"
    description: str = "Mock tool for testing idempotency"
    risk_level: RiskLevel = RiskLevel.LOW
    input_schema: type[DummyArgs] = DummyArgs

    def __init__(self) -> None:
        super().__init__()
        self.invocation_count = 0

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        self.invocation_count += 1
        args = DummyArgs(**kwargs)
        if args.delay > 0:
            await asyncio.sleep(args.delay)
        if args.should_fail:
            if args.fail_transient:
                raise TimeoutError("Network connection timed out while executing command")
            raise ValueError(f"Invalid command argument: {args.command}")
        return {
            "status": "success",
            "command": args.command,
            "secret_key": args.secret_key,
            "invocation_count": self.invocation_count,
        }


class MockToolRegistry:
    def __init__(self, tool: BaseTool[Any, Any]) -> None:
        self.tool = tool

    def get(self, name: str) -> BaseTool[Any, Any]:
        if name == self.tool.name:
            return self.tool
        raise KeyError(f"Tool {name} not found")


class MockPlanToolPort(IToolPort):
    def __init__(self) -> None:
        self.call_count = 0

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        self.call_count += 1
        return ToolExecutionResult(
            request_id=request.execution_id or "req-1",
            tool_name=request.tool_name,
            success=True,
            output=f"Executed {request.tool_name}",
        )

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        request_id: str | None = None,
        tool_policy: Any = None,
    ) -> ToolExecutionResult:
        self.call_count += 1
        return ToolExecutionResult(
            request_id=request_id or "req-1",
            tool_name=tool_name,
            success=True,
            output=f"Executed {tool_name}",
        )


# =========================================================================
# 1. Unit Tests: In-Memory & SQLite Store Basics & State Machine
# =========================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("store_cls", [InMemoryIdempotencyStore, SqliteIdempotencyStore])
async def test_store_happy_path_and_caching(store_cls: type) -> None:
    store = store_cls()
    tenant = "tenant-alpha"
    user = "user-123"
    key = "idem-key-001"
    payload = {"tool": "terminal", "args": {"cmd": "ls"}}
    fp = compute_payload_fingerprint(payload)

    # First call: registers and returns True (should execute)
    rec, should_exec = await store.start_execution(tenant, user, key, fp)
    assert should_exec is True
    assert rec.state == IdempotencyState.RUNNING

    # Complete execution with response
    response_payload = {"output": "file1.txt\nfile2.txt"}
    completed_rec = await store.complete_execution(tenant, user, key, response_payload)
    assert completed_rec.state == IdempotencyState.SUCCEEDED
    assert completed_rec.response == response_payload

    # Duplicate call with identical payload: returns False (replay cached result)
    rec2, should_exec2 = await store.start_execution(tenant, user, key, fp)
    assert should_exec2 is False
    assert rec2.state == IdempotencyState.SUCCEEDED
    assert rec2.response == response_payload


@pytest.mark.asyncio
@pytest.mark.parametrize("store_cls", [InMemoryIdempotencyStore, SqliteIdempotencyStore])
async def test_store_payload_mismatch_raises_conflict(store_cls: type) -> None:
    store = store_cls()
    tenant = "tenant-alpha"
    user = "user-123"
    key = "idem-key-002"

    fp1 = compute_payload_fingerprint({"tool": "terminal", "cmd": "ls"})
    fp2 = compute_payload_fingerprint({"tool": "terminal", "cmd": "rm -rf /"})

    await store.start_execution(tenant, user, key, fp1)

    # Different payload with the exact same key MUST raise IdempotencyPayloadMismatchError
    with pytest.raises(IdempotencyPayloadMismatchError):
        await store.start_execution(tenant, user, key, fp2)


@pytest.mark.asyncio
@pytest.mark.parametrize("store_cls", [InMemoryIdempotencyStore, SqliteIdempotencyStore])
async def test_store_concurrent_requests_atomicity(store_cls: type) -> None:
    store = store_cls()
    tenant = "tenant-alpha"
    user = "user-123"
    key = "idem-key-concurrent"
    fp = compute_payload_fingerprint({"task": "heavy_job"})

    async def try_start() -> bool:
        try:
            _, should_exec = await store.start_execution(tenant, user, key, fp)
            return should_exec
        except IdempotencyConflictError:
            return False

    # Launch 10 simultaneous start requests
    results = await asyncio.gather(*[try_start() for _ in range(10)])

    # Exactly ONE request should be granted execution
    assert results.count(True) == 1
    # The other 9 should be rejected with conflict
    assert results.count(False) == 9


@pytest.mark.asyncio
@pytest.mark.parametrize("store_cls", [InMemoryIdempotencyStore, SqliteIdempotencyStore])
async def test_store_failed_transient_retry_allowed(store_cls: type) -> None:
    store = store_cls()
    tenant = "tenant-alpha"
    user = "user-123"
    key = "idem-key-transient"
    fp = compute_payload_fingerprint({"cmd": "curl api.remote.com"})

    rec, should_exec = await store.start_execution(tenant, user, key, fp)
    assert should_exec is True

    # Mark as transient failure (e.g. timeout)
    await store.fail_execution(
        tenant,
        user,
        key,
        TimeoutError("Connection timed out"),
        state=IdempotencyState.FAILED_TRANSIENT,
    )

    # Retry with the same key should be ALLOWED
    retry_rec, retry_should_exec = await store.start_execution(tenant, user, key, fp)
    assert retry_should_exec is True
    assert retry_rec.state == IdempotencyState.RUNNING

    # Complete successfully on retry
    await store.complete_execution(tenant, user, key, {"status": "ok"})
    rec_final = await store.get(tenant, user, key)
    assert rec_final is not None
    assert rec_final.state == IdempotencyState.SUCCEEDED


@pytest.mark.asyncio
@pytest.mark.parametrize("store_cls", [InMemoryIdempotencyStore, SqliteIdempotencyStore])
async def test_store_failed_terminal_cached_no_retry(store_cls: type) -> None:
    store = store_cls()
    tenant = "tenant-alpha"
    user = "user-123"
    key = "idem-key-terminal"
    fp = compute_payload_fingerprint({"cmd": "invalid_command"})

    await store.start_execution(tenant, user, key, fp)
    await store.fail_execution(
        tenant,
        user,
        key,
        ValueError("Command not found"),
        state=IdempotencyState.FAILED_TERMINAL,
    )

    # Subsequent request MUST return cached failure (should_exec is False)
    rec, should_exec = await store.start_execution(tenant, user, key, fp)
    assert should_exec is False
    assert rec.state == IdempotencyState.FAILED_TERMINAL
    assert "Command not found" in str(rec.error_message)


@pytest.mark.asyncio
@pytest.mark.parametrize("store_cls", [InMemoryIdempotencyStore, SqliteIdempotencyStore])
async def test_store_ttl_expiry_allows_reuse(store_cls: type) -> None:
    store = store_cls()
    tenant = "tenant-alpha"
    user = "user-123"
    key = "idem-key-ttl"
    fp = compute_payload_fingerprint({"cmd": "test"})

    # Set TTL to 0.05 seconds
    rec, should_exec = await store.start_execution(tenant, user, key, fp, ttl_seconds=0.05)
    assert should_exec is True
    await store.complete_execution(tenant, user, key, {"result": "first"})

    # Wait for expiration
    await asyncio.sleep(0.08)

    # Key should now be expired and reusable as new
    rec2, should_exec2 = await store.start_execution(tenant, user, key, fp)
    assert should_exec2 is True
    assert rec2.state == IdempotencyState.RUNNING


@pytest.mark.asyncio
@pytest.mark.parametrize("store_cls", [InMemoryIdempotencyStore, SqliteIdempotencyStore])
async def test_store_cross_tenant_isolation(store_cls: type) -> None:
    store = store_cls()
    user = "operator-1"
    key = "shared-uuid-key"
    fp = compute_payload_fingerprint({"action": "restart_service"})

    # Tenant A executes
    rec_a, should_exec_a = await store.start_execution("tenant-A", user, key, fp)
    assert should_exec_a is True
    await store.complete_execution("tenant-A", user, key, {"tenant": "A"})

    # Tenant B uses the exact same user and key -> completely independent!
    rec_b, should_exec_b = await store.start_execution("tenant-B", user, key, fp)
    assert should_exec_b is True
    await store.complete_execution("tenant-B", user, key, {"tenant": "B"})

    # Validate cached outputs remain isolated
    item_a = await store.get("tenant-A", user, key)
    item_b = await store.get("tenant-B", user, key)
    assert item_a is not None and item_a.response == {"tenant": "A"}
    assert item_b is not None and item_b.response == {"tenant": "B"}


@pytest.mark.asyncio
@pytest.mark.parametrize("store_cls", [InMemoryIdempotencyStore, SqliteIdempotencyStore])
async def test_store_response_cache_secret_sanitization(store_cls: type) -> None:
    store = store_cls()
    tenant = "tenant-security"
    user = "user-1"
    key = "idem-key-secrets"
    fp = compute_payload_fingerprint({"cmd": "dump_env"})

    await store.start_execution(tenant, user, key, fp)
    raw_response = {
        "api_key": "sk-test-secret-123456",
        "access_token": "bearer eyJhbGciOi...",
        "status": "active",
        "nested": {"password": "super-secret-password"},
    }
    rec = await store.complete_execution(tenant, user, key, raw_response)

    # Verify secrets were stripped
    assert rec.response is not None
    assert rec.response["api_key"] == "[REDACTED_SECRET]"
    assert rec.response["access_token"] == "[REDACTED_SECRET]"
    assert rec.response["status"] == "active"
    assert rec.response["nested"]["password"] == "[REDACTED_SECRET]"


# =========================================================================
# 2. CQRS CommandBus Layer Idempotency Tests
# =========================================================================


@pytest.mark.asyncio
async def test_cqrs_command_handler_idempotency() -> None:
    tool = MockEchoTool()
    registry = MockToolRegistry(tool)
    security_guard = SecurityGuard(SystemConfig().security)
    event_bus = EventBus()
    store = InMemoryIdempotencyStore()

    handler = ExecuteToolCommandHandler(
        registry=registry,  # type: ignore[arg-type]
        security_guard=security_guard,
        event_bus=event_bus,
        idempotency_store=store,
    )

    cmd = ExecuteToolCommand(
        tool_name="mock_echo_tool",
        arguments={"command": "date", "secret_key": "sk-topsecret"},
        user_id="user-cqrs",
        tenant_id="tenant-cqrs",
        idempotency_key="key-cqrs-001",
    )

    # 1. First execution -> tool actually runs
    res1 = await handler(cmd)
    assert res1["status"] == "success"
    assert tool.invocation_count == 1
    # Secret key in cached output was sanitized
    assert res1["secret_key"] == "[REDACTED_SECRET]"

    # 2. Duplicate command -> tool is NOT re-executed, cached output returned
    res2 = await handler(cmd)
    assert res2["status"] == "success"
    assert tool.invocation_count == 1  # Still 1!
    assert res2["secret_key"] == "[REDACTED_SECRET]"

    # 3. Same key with different payload -> raises IdempotencyPayloadMismatchError
    cmd_mismatch = ExecuteToolCommand(
        tool_name="mock_echo_tool",
        arguments={"command": "whoami"},
        user_id="user-cqrs",
        tenant_id="tenant-cqrs",
        idempotency_key="key-cqrs-001",
    )
    with pytest.raises(IdempotencyPayloadMismatchError):
        await handler(cmd_mismatch)


# =========================================================================
# 3. DAG Execution Engine Layer Idempotency Tests
# =========================================================================


@pytest.mark.asyncio
async def test_dag_execution_engine_idempotency() -> None:
    store = InMemoryIdempotencyStore()
    engine = PlanGraphExecutionEngine(idempotency_port=store)
    tool_port = MockPlanToolPort()

    ctx = PlanningContext(
        goal_component=PlanningGoal(
            goal=AgentGoal(description="Run automated security health check")
        ),
        constraints_component=PlanningConstraints(),
    )

    # First plan execution
    plan_graph1, results1, trace1 = await engine.execute_plan(
        ctx=ctx,
        tool_port=tool_port,
        session_id="session-dag-1",
        idempotency_key="dag-idem-001",
        tenant_id="tenant-dag",
        user_id="user-dag",
    )
    initial_tool_calls = tool_port.call_count
    assert initial_tool_calls > 0

    # Second execution with same idempotency key -> returns cached result without running tools again
    plan_graph2, results2, trace2 = await engine.execute_plan(
        ctx=ctx,
        tool_port=tool_port,
        session_id="session-dag-1",
        idempotency_key="dag-idem-001",
        tenant_id="tenant-dag",
        user_id="user-dag",
    )
    assert tool_port.call_count == initial_tool_calls  # No additional tool calls!
    assert plan_graph2 == plan_graph1


# =========================================================================
# 4. HTTP API Endpoints Tests (/api/tools/execute & /api/v1/dag/execute)
# =========================================================================


def test_api_tools_execute_idempotency_header() -> None:
    app = create_app()
    client = TestClient(app)

    headers = {
        "Idempotency-Key": "http-idem-tool-001",
        "X-NexusAI-API-Key": "nx_test_admin_key_123",
    }
    payload = {
        "tool_name": "workspace_git_status",
        "arguments": {},
    }

    # First request -> 200 OK with X-Cache: MISS
    resp1 = client.post("/api/tools/execute", json=payload, headers=headers)
    assert resp1.status_code == 200
    assert resp1.headers.get("X-Cache") == "MISS"
    data1 = resp1.json()
    assert data1["success"] is True

    # Duplicate request -> 200 OK with X-Cache: HIT
    resp2 = client.post("/api/tools/execute", json=payload, headers=headers)
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Cache") == "HIT"
    assert resp2.json() == data1

    # Payload mismatch with same key -> 409 Conflict
    mismatch_payload = {
        "tool_name": "workspace_list_directory",
        "arguments": {"directory_path": "."},
    }
    resp_conflict = client.post("/api/tools/execute", json=mismatch_payload, headers=headers)
    assert resp_conflict.status_code == 409
    assert "payload mismatch" in resp_conflict.json()["detail"].lower()


def test_api_dag_execute_idempotency() -> None:
    app = create_app()
    client = TestClient(app)

    headers = {
        "Idempotency-Key": "http-idem-dag-001",
        "X-NexusAI-API-Key": "nx_test_admin_key_123",
    }
    payload = {
        "plan_id": "incident_response",
    }

    # 1. First execution request -> 200 OK with X-Cache: MISS
    resp1 = client.post("/api/v1/dag/execute", json=payload, headers=headers)
    assert resp1.status_code == 200
    assert resp1.headers.get("X-Cache") == "MISS"
    data1 = resp1.json()
    assert data1["status"] == "EXECUTION_STARTED"

    # 2. Duplicate execution request -> 200 OK with X-Cache: HIT
    resp2 = client.post("/api/v1/dag/execute", json=payload, headers=headers)
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Cache") == "HIT"
    assert resp2.json()["status"] == "EXECUTION_STARTED"

    # 3. Payload mismatch with same key -> 409 Conflict
    mismatch_payload = {
        "plan_id": "incident_response",
        "simulate_failure_step": "step_2",
    }
    resp_conflict = client.post("/api/v1/dag/execute", json=mismatch_payload, headers=headers)
    assert resp_conflict.status_code == 409
    assert "payload mismatch" in resp_conflict.json()["detail"].lower()
