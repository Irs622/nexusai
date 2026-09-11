"""Unit tests for Server-Side ApprovalTokenService."""

import time

import pytest

from nexusai.core.errors import SecurityError
from nexusai.security.approval_token import ApprovalTokenService


def test_approval_token_issuance_and_validation() -> None:
    service = ApprovalTokenService(secret="test-secret-key-12345", default_ttl_seconds=300.0)
    args = {"command": "ls -la /tmp"}
    token, expires_at = service.create_token(
        tool_name="execute_terminal",
        arguments=args,
        user_id="alice",
        execution_id="exec-001",
    )

    assert token.startswith(ApprovalTokenService.TOKEN_PREFIX)
    assert expires_at > time.time()

    # Valid validation & single-use consumption
    assert (
        service.validate_and_consume(
            token=token,
            tool_name="execute_terminal",
            arguments=args,
            user_id="alice",
            execution_id="exec-001",
        )
        is True
    )


def test_approval_token_replay_rejected() -> None:
    service = ApprovalTokenService(secret="test-secret-key-12345")
    args = {"path": "/var/log/app.log"}
    token, _ = service.create_token(
        tool_name="delete_file",
        arguments=args,
    )

    # First consumption succeeds
    assert (
        service.validate_and_consume(
            token=token,
            tool_name="delete_file",
            arguments=args,
        )
        is True
    )

    # Replay attempt must be rejected with SecurityError
    with pytest.raises(SecurityError) as exc_info:
        service.validate_and_consume(
            token=token,
            tool_name="delete_file",
            arguments=args,
        )
    assert "replay detected" in str(exc_info.value).lower()


def test_approval_token_expired_rejected() -> None:
    service = ApprovalTokenService(secret="test-secret-key-12345")
    args = {"command": "cat /etc/hosts"}
    # Create an already expired token (ttl = -10 seconds)
    token, _ = service.create_token(
        tool_name="execute_terminal",
        arguments=args,
        ttl_seconds=-10.0,
    )

    with pytest.raises(SecurityError) as exc_info:
        service.validate_and_consume(
            token=token,
            tool_name="execute_terminal",
            arguments=args,
        )
    assert "expired" in str(exc_info.value).lower()


def test_approval_token_argument_tampering_rejected() -> None:
    service = ApprovalTokenService(secret="test-secret-key-12345")
    args = {"command": "echo safe"}
    token, _ = service.create_token(
        tool_name="execute_terminal",
        arguments=args,
    )

    # Attempt validation with tampered command
    tampered_args = {"command": "rm -rf /"}
    with pytest.raises(SecurityError) as exc_info:
        service.validate_and_consume(
            token=token,
            tool_name="execute_terminal",
            arguments=tampered_args,
        )
    assert "mismatch" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


def test_approval_token_tool_mismatch_rejected() -> None:
    service = ApprovalTokenService(secret="test-secret-key-12345")
    args = {"command": "ls"}
    token, _ = service.create_token(
        tool_name="terminal",
        arguments=args,
    )

    # Attempt validation for a different tool (delete_file)
    with pytest.raises(SecurityError) as exc_info:
        service.validate_and_consume(
            token=token,
            tool_name="delete_file",
            arguments=args,
        )
    assert "mismatch" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


def test_approval_token_identity_binding() -> None:
    service = ApprovalTokenService(secret="test-secret-key-12345")
    args = {"param": "value"}
    token, _ = service.create_token(
        tool_name="sensitive_tool",
        arguments=args,
        user_id="admin",
    )

    # Different user cannot consume the token
    with pytest.raises(SecurityError) as exc_info:
        service.validate_and_consume(
            token=token,
            tool_name="sensitive_tool",
            arguments=args,
            user_id="attacker",
        )
    assert "mismatch" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


def test_approval_token_malformed_token_rejected() -> None:
    service = ApprovalTokenService(secret="test-secret-key-12345")

    with pytest.raises(SecurityError) as exc1:
        service.validate_and_consume(
            token="invalid_prefix_token",
            tool_name="tool",
            arguments={},
        )
    assert "prefix" in str(exc1.value).lower()

    with pytest.raises(SecurityError) as exc2:
        service.validate_and_consume(
            token=f"{ApprovalTokenService.TOKEN_PREFIX}invalid.segments",
            tool_name="tool",
            arguments={},
        )
    assert "segments" in str(exc2.value).lower()
