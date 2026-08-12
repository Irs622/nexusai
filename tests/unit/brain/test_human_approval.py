"""Unit test suite for P3-6 Human Approval domain models, Risk Evaluator precedence, and ActionBinding digests."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalGrant,
    ApprovalStatus,
    HumanApprovalDecision,
    HumanApprovalRequest,
    RiskLevel,
    evaluate_action_risk,
)
from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine


def test_action_binding_digest_determinism() -> None:
    """Test ActionBinding SHA-256 action_digest computation is deterministic regardless of capability set ordering."""
    b1 = ActionBinding(
        session_id="sess-1",
        execution_id="exec-1",
        plan_fingerprint="fingerprint-hash-123",
        node_id="node-1",
        tool_id="terminal",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.FILE_READ, ToolCapability.PROCESS_EXEC}),
        resource_scope="/app",
    )
    b2 = ActionBinding(
        session_id="sess-1",
        execution_id="exec-1",
        plan_fingerprint="fingerprint-hash-123",
        node_id="node-1",
        tool_id="terminal",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC, ToolCapability.FILE_READ}),
        resource_scope="/app",
    )

    assert b1.action_digest == b2.action_digest, "Action digests must match for identical binding parameters"


def test_risk_evaluator_hierarchical_precedence() -> None:
    """Test evaluate_action_risk enforces strict precedence: CRITICAL > HIGH > MEDIUM > LOW."""
    # FILE_READ -> LOW
    assert evaluate_action_risk(frozenset({ToolCapability.FILE_READ})) == RiskLevel.LOW

    # FILE_READ + FILE_WRITE -> MEDIUM
    assert evaluate_action_risk(frozenset({ToolCapability.FILE_READ, ToolCapability.FILE_WRITE})) == RiskLevel.MEDIUM

    # FILE_WRITE + PROCESS_EXEC -> HIGH
    assert evaluate_action_risk(frozenset({ToolCapability.FILE_WRITE, ToolCapability.PROCESS_EXEC})) == RiskLevel.HIGH

    # FILE_WRITE + SECRET_ACCESS -> CRITICAL
    assert evaluate_action_risk(frozenset({ToolCapability.FILE_WRITE, ToolCapability.SECRET_ACCESS})) == RiskLevel.CRITICAL


def test_secret_sanitization_across_all_approval_fields() -> None:
    """Test secret sanitization is enforced across prompt_summary, decision reasons, and metadata."""
    binding = ActionBinding(
        session_id="sess-1",
        execution_id="exec-1",
        plan_fingerprint="fp1",
        node_id="n1",
        tool_id="t1",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.FILE_READ}),
    )

    req = HumanApprovalRequest(
        approval_id="app-1",
        binding=binding,
        risk_level=RiskLevel.MEDIUM,
        prompt_summary="Run script with api_key=sk-secret-12345",
        metadata={"token": "bearer-secret-token"},
    )
    assert req.prompt_summary == "[REDACTED_SECRET]"
    assert req.metadata["token"] == "[REDACTED_SECRET]"

    dec = HumanApprovalDecision(
        approval_id="app-1",
        status=ApprovalStatus.APPROVED,
        actor="op@co.com",
        reason="Approved using authorization_key=secret-key",
    )
    assert dec.reason == "[REDACTED_SECRET]"


if __name__ == "__main__":
    test_action_binding_digest_determinism()
    test_risk_evaluator_hierarchical_precedence()
    test_secret_sanitization_across_all_approval_fields()
    print("ALL P3-6 HUMAN APPROVAL UNIT TESTS PASSED SUCCESSFULLY!")
