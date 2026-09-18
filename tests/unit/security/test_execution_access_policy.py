"""Unit tests for ExecutionAccessPolicy (ADR-0035, NEX-SEC-001, NEX-SEC-002)."""

import pytest

from nexusai.core.errors import AuthenticationError, AuthorizationError
from nexusai.security.execution_policy import ExecutionAccessPolicy
from nexusai.security.identity import Identity, Role


@pytest.fixture
def viewer_identity() -> Identity:
    return Identity(tenant_id="tenant-alpha", user_id="viewer-1", role=Role.VIEWER)


@pytest.fixture
def operator_identity() -> Identity:
    return Identity(tenant_id="tenant-alpha", user_id="operator-1", role=Role.OPERATOR)


@pytest.fixture
def admin_identity() -> Identity:
    return Identity(tenant_id="tenant-alpha", user_id="admin-1", role=Role.ADMIN)


@pytest.fixture
def system_identity() -> Identity:
    return Identity(tenant_id="system-internal", user_id="sys-svc", role=Role.SYSTEM)


def test_execution_read_authorization_matrix(
    viewer_identity: Identity,
    operator_identity: Identity,
    admin_identity: Identity,
    system_identity: Identity,
) -> None:
    """Verify execution state read access matrix across roles and tenant boundaries."""
    # 1. Unauthenticated -> False
    assert ExecutionAccessPolicy.can_read(None, "tenant-alpha") is False

    # 2. Own tenant -> Viewer and Operator can read
    assert ExecutionAccessPolicy.can_read(viewer_identity, "tenant-alpha") is True
    assert ExecutionAccessPolicy.can_read(operator_identity, "tenant-alpha") is True

    # 3. Cross tenant -> Viewer and Operator CANNOT read (BOLA prevention)
    assert ExecutionAccessPolicy.can_read(viewer_identity, "tenant-beta") is False
    assert ExecutionAccessPolicy.can_read(operator_identity, "tenant-beta") is False

    # 4. Admin and System -> Cross tenant permitted
    assert ExecutionAccessPolicy.can_read(admin_identity, "tenant-beta") is True
    assert ExecutionAccessPolicy.can_read(system_identity, "tenant-alpha") is True


def test_execution_cancel_authorization_matrix(
    viewer_identity: Identity,
    operator_identity: Identity,
    admin_identity: Identity,
    system_identity: Identity,
) -> None:
    """Verify execution cancellation authorization matrix across roles and tenant boundaries."""
    # 1. Unauthenticated -> False
    assert ExecutionAccessPolicy.can_cancel(None, "tenant-alpha") is False

    # 2. Viewer CANNOT cancel even in own tenant (read-only invariant)
    assert ExecutionAccessPolicy.can_cancel(viewer_identity, "tenant-alpha") is False
    assert ExecutionAccessPolicy.can_cancel(viewer_identity, "tenant-beta") is False

    # 3. Operator can cancel in own tenant, but CANNOT cancel cross-tenant (BOLA mutation prevention)
    assert ExecutionAccessPolicy.can_cancel(operator_identity, "tenant-alpha") is True
    assert ExecutionAccessPolicy.can_cancel(operator_identity, "tenant-beta") is False

    # 4. Admin and System can cancel across tenants
    assert ExecutionAccessPolicy.can_cancel(admin_identity, "tenant-alpha") is True
    assert ExecutionAccessPolicy.can_cancel(admin_identity, "tenant-beta") is True
    assert ExecutionAccessPolicy.can_cancel(system_identity, "tenant-alpha") is True


def test_authorize_read_exceptions(
    viewer_identity: Identity,
    operator_identity: Identity,
    admin_identity: Identity,
) -> None:
    """Verify authorize_read raises explicit AuthenticationError and AuthorizationError."""
    # Unauthenticated raises AuthenticationError
    with pytest.raises(AuthenticationError):
        ExecutionAccessPolicy.authorize_read(None, "tenant-alpha")

    # Cross-tenant non-admin raises AuthorizationError
    with pytest.raises(AuthorizationError) as exc_info:
        ExecutionAccessPolicy.authorize_read(operator_identity, "tenant-beta")
    assert "Cross-tenant execution access denied" in str(exc_info.value)

    # Permitted calls do not raise
    ExecutionAccessPolicy.authorize_read(viewer_identity, "tenant-alpha")
    ExecutionAccessPolicy.authorize_read(operator_identity, "tenant-alpha")
    ExecutionAccessPolicy.authorize_read(admin_identity, "tenant-beta")


def test_authorize_cancel_exceptions(
    viewer_identity: Identity,
    operator_identity: Identity,
    admin_identity: Identity,
) -> None:
    """Verify authorize_cancel raises explicit AuthenticationError and AuthorizationError."""
    # Unauthenticated raises AuthenticationError
    with pytest.raises(AuthenticationError):
        ExecutionAccessPolicy.authorize_cancel(None, "tenant-alpha")

    # Viewer raises AuthorizationError
    with pytest.raises(AuthorizationError) as exc_info:
        ExecutionAccessPolicy.authorize_cancel(viewer_identity, "tenant-alpha")
    assert "Viewer role cannot cancel executions" in str(exc_info.value)

    # Cross-tenant operator raises AuthorizationError
    with pytest.raises(AuthorizationError) as exc_info:
        ExecutionAccessPolicy.authorize_cancel(operator_identity, "tenant-beta")
    assert "Cross-tenant execution cancellation denied" in str(exc_info.value)

    # Permitted calls do not raise
    ExecutionAccessPolicy.authorize_cancel(operator_identity, "tenant-alpha")
    ExecutionAccessPolicy.authorize_cancel(admin_identity, "tenant-beta")
