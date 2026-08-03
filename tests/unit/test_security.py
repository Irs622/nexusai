"""Unit tests for Security Guard and Sanitizer."""

import pytest
from nexusai.security.guard import SecurityGuard, RiskLevel, ActionRequest
from nexusai.core.errors import SecurityError


def test_security_low_risk_auto_permit(security_guard: SecurityGuard) -> None:
    req = ActionRequest(
        action_name="GetClipboard",
        risk_level=RiskLevel.LOW,
        description="Reads current clipboard text",
        parameters={},
    )
    assert security_guard.evaluate_permission(req) is True


def test_security_forbidden_command_sanitization(security_guard: SecurityGuard) -> None:
    req = ActionRequest(
        action_name="RunTerminalCommand",
        risk_level=RiskLevel.HIGH,
        description="Runs terminal command",
        parameters={"command": "rm -rf /"},
    )
    with pytest.raises(SecurityError):
        security_guard.evaluate_permission(req, user_confirmed=True)


def test_security_protected_path_denied(security_guard: SecurityGuard) -> None:
    req = ActionRequest(
        action_name="WriteSystemFile",
        risk_level=RiskLevel.HIGH,
        description="Overwrites system file",
        parameters={"path": "/System/Library/CoreServices/boot.efi"},
    )
    with pytest.raises(SecurityError):
        security_guard.evaluate_permission(req, user_confirmed=True)


def test_security_high_risk_requires_confirmation(security_guard: SecurityGuard) -> None:
    req = ActionRequest(
        action_name="DeleteUserDirectory",
        risk_level=RiskLevel.HIGH,
        description="Deletes directory",
        parameters={"path": "temp_folder"},
    )
    assert security_guard.evaluate_permission(req, user_confirmed=False) is False
    assert security_guard.evaluate_permission(req, user_confirmed=True) is True
