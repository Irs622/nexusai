"""Unit tests for RbacEngine and SecurityGuard authorization enforcement."""

import pytest

from nexusai.core.config import SecuritySettings
from nexusai.core.errors import AuthorizationError
from nexusai.security.authorization import RbacEngine
from nexusai.security.guard import ActionRequest, RiskLevel, SecurityGuard
from nexusai.security.identity import ROLE_HIERARCHY, Identity, Role, TenantContext


def test_role_hierarchy_values() -> None:
    """Verify role hierarchy precedence values."""
    assert ROLE_HIERARCHY[Role.VIEWER] < ROLE_HIERARCHY[Role.OPERATOR]
    assert ROLE_HIERARCHY[Role.OPERATOR] < ROLE_HIERARCHY[Role.ADMIN]
    assert ROLE_HIERARCHY[Role.ADMIN] <= ROLE_HIERARCHY[Role.SYSTEM]


def test_rbac_tool_access_viewer() -> None:
    """Verify viewer role cannot execute any tools regardless of risk level."""
    rbac = RbacEngine()
    viewer = Identity(tenant_id="tenant-1", user_id="viewer-1", role=Role.VIEWER)

    for risk in [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]:
        assert rbac.check_tool_access(viewer, risk) is False


def test_rbac_tool_access_operator() -> None:
    """Verify operator role can execute LOW and MEDIUM risk tools, but blocked on HIGH and CRITICAL."""
    rbac = RbacEngine()
    operator = Identity(tenant_id="tenant-1", user_id="operator-1", role=Role.OPERATOR)

    # Allowed
    assert rbac.check_tool_access(operator, RiskLevel.LOW) is True
    assert rbac.check_tool_access(operator, RiskLevel.MEDIUM) is True

    # Blocked
    assert rbac.check_tool_access(operator, RiskLevel.HIGH) is False
    assert rbac.check_tool_access(operator, RiskLevel.CRITICAL) is False


def test_rbac_tool_access_admin_and_system() -> None:
    """Verify admin and system roles can execute tools across all risk levels."""
    rbac = RbacEngine()
    admin = Identity(tenant_id="tenant-1", user_id="admin-1", role=Role.ADMIN)
    system = Identity(tenant_id="tenant-1", user_id="system-1", role=Role.SYSTEM)

    for risk in [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]:
        assert rbac.check_tool_access(admin, risk) is True
        assert rbac.check_tool_access(system, risk) is True


def test_rbac_http_method_access() -> None:
    """Verify viewer cannot execute mutating HTTP methods."""
    rbac = RbacEngine()
    viewer = Identity(tenant_id="tenant-1", user_id="viewer-1", role=Role.VIEWER)
    operator = Identity(tenant_id="tenant-1", user_id="operator-1", role=Role.OPERATOR)

    assert rbac.check_http_access(viewer, "GET", "/api/tools") is True
    assert rbac.check_http_access(viewer, "HEAD", "/api/tools") is True
    assert rbac.check_http_access(viewer, "OPTIONS", "/api/tools") is True

    assert rbac.check_http_access(viewer, "POST", "/api/tools/execute") is False
    assert rbac.check_http_access(viewer, "DELETE", "/api/v1/plans/123") is False
    assert rbac.check_http_access(viewer, "PUT", "/api/v1/config") is False

    # Operator is allowed mutating methods
    assert rbac.check_http_access(operator, "POST", "/api/chat") is True


def test_rbac_anti_escalation() -> None:
    """Verify callers cannot assign or escalate roles beyond their authority."""
    rbac = RbacEngine()
    viewer = Identity(tenant_id="tenant-1", user_id="viewer-1", role=Role.VIEWER)
    operator = Identity(tenant_id="tenant-1", user_id="operator-1", role=Role.OPERATOR)
    admin = Identity(tenant_id="tenant-1", user_id="admin-1", role=Role.ADMIN)

    # 1. Non-admin cannot assign any roles
    with pytest.raises(AuthorizationError, match="cannot manage or assign roles"):
        rbac.validate_role_assignment(
            actor=viewer, target_role=Role.VIEWER, target_user_id="target-1"
        )

    with pytest.raises(AuthorizationError, match="cannot manage or assign roles"):
        rbac.validate_role_assignment(
            actor=operator, target_role=Role.OPERATOR, target_user_id="target-1"
        )

    # 2. Caller cannot escalate beyond their own level
    with pytest.raises(
        AuthorizationError, match="Cannot assign role 'system' exceeding caller role 'admin'"
    ):
        rbac.validate_role_assignment(
            actor=admin, target_role=Role.SYSTEM, target_user_id="target-2"
        )

    # 3. Admin assigning operator or viewer or admin to other users is allowed
    assert (
        rbac.validate_role_assignment(
            actor=admin, target_role=Role.OPERATOR, target_user_id="target-3"
        )
        is True
    )
    assert (
        rbac.validate_role_assignment(
            actor=admin, target_role=Role.VIEWER, target_user_id="target-3"
        )
        is True
    )
    assert (
        rbac.validate_role_assignment(
            actor=admin, target_role=Role.ADMIN, target_user_id="target-3"
        )
        is True
    )


def test_security_guard_with_rbac_enforcement() -> None:
    """Verify SecurityGuard enforces RBAC rules when Identity is provided."""
    settings = SecuritySettings(strict_mode=True, auto_approve_low_risk=False)
    guard = SecurityGuard(settings=settings)

    viewer = Identity(tenant_id="tenant-1", user_id="viewer-1", role=Role.VIEWER)
    operator = Identity(tenant_id="tenant-1", user_id="operator-1", role=Role.OPERATOR)
    admin = Identity(tenant_id="tenant-1", user_id="admin-1", role=Role.ADMIN)

    req_low = ActionRequest(
        action_name="tool:read_file",
        risk_level=RiskLevel.LOW,
        description="Reads file",
        parameters={"path": "/tmp/test.txt"},
    )
    req_high = ActionRequest(
        action_name="tool:execute_terminal",
        risk_level=RiskLevel.HIGH,
        description="Executes shell",
        parameters={"command": "ls"},
    )

    # Viewer attempting low risk tool -> blocked by RBAC
    token = TenantContext.set_current_identity(viewer)
    try:
        assert guard.evaluate_permission(req_low, user_id=viewer.user_id) is False
    finally:
        TenantContext.reset(token)

    # Operator attempting low risk tool -> allowed by RBAC
    token = TenantContext.set_current_identity(operator)
    try:
        assert guard.evaluate_permission(req_low, user_id=operator.user_id) is True
        # Operator attempting high risk tool -> blocked by RBAC
        assert guard.evaluate_permission(req_high, user_id=operator.user_id) is False
    finally:
        TenantContext.reset(token)

    # Admin attempting high risk tool with approval token -> allowed
    token = TenantContext.set_current_identity(admin)
    try:
        appr_token, _ = guard.approval_service.create_token(
            tool_name="execute_terminal",
            arguments={"command": "ls"},
            user_id=admin.user_id,
        )
        assert (
            guard.evaluate_permission(req_high, approval_token=appr_token, user_id=admin.user_id)
            is True
        )
    finally:
        TenantContext.reset(token)
