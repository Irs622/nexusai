"""Unit tests for ApiKeyService, AuthMiddleware, and TenantContext."""

import time

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from nexusai.core.errors import AuthenticationError, RateLimitExceededError
from nexusai.security.authentication import ApiKeyService, AuthMiddleware
from nexusai.security.identity import Identity, Role, TenantContext


def test_api_key_generation_and_storage() -> None:
    """Verify API keys are generated with secure prefixes and zero plaintext storage."""
    service = ApiKeyService()
    raw_key, record = service.create_api_key(
        tenant_id="tenant-alpha",
        user_id="user-001",
        role=Role.OPERATOR,
        name="alpha-operator-key",
    )

    assert raw_key.startswith(ApiKeyService.KEY_PREFIX)
    assert record.tenant_id == "tenant-alpha"
    assert record.user_id == "user-001"
    assert record.role == Role.OPERATOR
    assert record.name == "alpha-operator-key"
    assert not record.is_revoked

    # Zero plaintext storage verification
    for key_hash, stored_record in service._keys.items():
        assert raw_key not in key_hash
        assert raw_key != stored_record.key_hash


def test_api_key_authentication_success() -> None:
    """Verify authenticating with a valid raw key yields the correct Identity."""
    service = ApiKeyService()
    raw_key, record = service.create_api_key(
        tenant_id="tenant-beta",
        user_id="user-002",
        role=Role.ADMIN,
    )

    identity = service.authenticate(raw_key)
    assert identity.tenant_id == "tenant-beta"
    assert identity.user_id == "user-002"
    assert identity.role == Role.ADMIN
    assert identity.api_key_id == record.key_id


def test_api_key_authentication_invalid_key() -> None:
    """Verify invalid keys raise AuthenticationError."""
    service = ApiKeyService()
    service.create_api_key(tenant_id="tenant-1", user_id="u1", role=Role.VIEWER)

    with pytest.raises(AuthenticationError, match="Invalid API key"):
        service.authenticate("nxk_invalid_key_does_not_exist")

    with pytest.raises(AuthenticationError, match="Invalid API key"):
        service.authenticate("")


def test_api_key_revocation() -> None:
    """Verify revoking an API key immediately rejects subsequent authentication."""
    service = ApiKeyService()
    raw_key, record = service.create_api_key(
        tenant_id="tenant-gamma",
        user_id="user-003",
        role=Role.VIEWER,
    )

    # Valid before revocation
    assert service.authenticate(raw_key).user_id == "user-003"

    # Revoke key
    revoked = service.revoke_key(record.key_id)
    assert revoked is True

    # Immediate rejection
    with pytest.raises(AuthenticationError, match="API key has been revoked"):
        service.authenticate(raw_key)


def test_api_key_expiration() -> None:
    """Verify expired keys raise AuthenticationError."""
    service = ApiKeyService()
    # Expire in 1 millisecond
    raw_key, _ = service.create_api_key(
        tenant_id="tenant-delta",
        user_id="user-004",
        role=Role.OPERATOR,
        expires_in_seconds=0.001,
    )
    time.sleep(0.01)

    with pytest.raises(AuthenticationError, match="API key has expired"):
        service.authenticate(raw_key)


def test_api_key_rate_limiting() -> None:
    """Verify sliding-window rate limiting triggers RateLimitExceededError."""
    service = ApiKeyService(rate_limit_per_minute=3)
    _, record = service.create_api_key(
        tenant_id="tenant-rate",
        user_id="user-rate",
        role=Role.OPERATOR,
    )

    # 3 allowed requests
    service.check_rate_limit(record.key_id)
    service.check_rate_limit(record.key_id)
    service.check_rate_limit(record.key_id)

    # 4th exceeds 3 req/min
    with pytest.raises(
        RateLimitExceededError, match="Rate limit exceeded: max 3 requests per minute"
    ):
        service.check_rate_limit(record.key_id)


def test_tenant_context_vars() -> None:
    """Verify TenantContext isolation with ContextVar."""
    assert TenantContext.get() is None
    token = TenantContext.set("tenant-isolated-1")
    try:
        assert TenantContext.get() == "tenant-isolated-1"
        assert TenantContext.get_required() == "tenant-isolated-1"
    finally:
        TenantContext.reset(token)

    assert TenantContext.get() is None
    with pytest.raises(AuthenticationError, match="No active tenant context"):
        TenantContext.get_required()


def test_auth_middleware_flow() -> None:
    """Verify AuthMiddleware enforces authentication, allows exempt paths, and returns 401/429."""
    service = ApiKeyService(rate_limit_per_minute=2)
    raw_key, record = service.create_api_key(
        tenant_id="tenant-web",
        user_id="user-web",
        role=Role.OPERATOR,
    )

    async def health_endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def protected_endpoint(request: Request) -> JSONResponse:
        identity: Identity = request.state.identity
        return JSONResponse(
            {
                "tenant_id": identity.tenant_id,
                "user_id": identity.user_id,
                "role": identity.role.value,
            }
        )

    app = Starlette(
        routes=[
            Route("/health/live", health_endpoint, methods=["GET"]),
            Route("/api/data", protected_endpoint, methods=["GET"]),
        ]
    )
    app.add_middleware(
        AuthMiddleware,
        api_key_service=service,
        exempt_paths=["/health/live"],
    )

    client = TestClient(app)

    # 1. Exempt path succeeds without key
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    # 2. Protected path without header -> 401
    resp = client.get("/api/data")
    assert resp.status_code == 401
    assert "Missing 'X-NexusAI-API-Key' header" in resp.json()["detail"]

    # 3. Protected path with invalid header -> 401
    resp = client.get("/api/data", headers={"X-NexusAI-API-Key": "invalid-key"})
    assert resp.status_code == 401
    assert "Invalid API key" in resp.json()["detail"]

    # 4. Protected path with valid key -> 200 & identity populated
    resp = client.get("/api/data", headers={"X-NexusAI-API-Key": raw_key})
    assert resp.status_code == 200
    assert resp.json() == {
        "tenant_id": "tenant-web",
        "user_id": "user-web",
        "role": "operator",
    }

    # 5. Second request within limit -> 200
    resp = client.get("/api/data", headers={"X-NexusAI-API-Key": raw_key})
    assert resp.status_code == 200

    # 6. Third request exceeds 2 req/min -> 429
    resp = client.get("/api/data", headers={"X-NexusAI-API-Key": raw_key})
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.json()["detail"]
