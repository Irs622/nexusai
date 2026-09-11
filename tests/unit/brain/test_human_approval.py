"""Unit test suite for P3-6 Human Approval domain models, Risk Evaluator precedence, and ActionBinding digests."""

from __future__ import annotations

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalStatus,
    HumanApprovalDecision,
    HumanApprovalRequest,
    RiskLevel,
    evaluate_action_risk,
)


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

    assert (
        b1.action_digest == b2.action_digest
    ), "Action digests must match for identical binding parameters"


def test_risk_evaluator_hierarchical_precedence() -> None:
    """Test evaluate_action_risk enforces strict precedence: CRITICAL > HIGH > MEDIUM > LOW."""
    # FILE_READ -> LOW
    assert evaluate_action_risk(frozenset({ToolCapability.FILE_READ})) == RiskLevel.LOW

    # FILE_READ + FILE_WRITE -> MEDIUM
    assert (
        evaluate_action_risk(frozenset({ToolCapability.FILE_READ, ToolCapability.FILE_WRITE}))
        == RiskLevel.MEDIUM
    )

    # FILE_WRITE + PROCESS_EXEC -> HIGH
    assert (
        evaluate_action_risk(frozenset({ToolCapability.FILE_WRITE, ToolCapability.PROCESS_EXEC}))
        == RiskLevel.HIGH
    )

    # FILE_WRITE + SECRET_ACCESS -> CRITICAL
    assert (
        evaluate_action_risk(frozenset({ToolCapability.FILE_WRITE, ToolCapability.SECRET_ACCESS}))
        == RiskLevel.CRITICAL
    )


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
        prompt_summary="Run script with " + "api_" + "key=sk-secret-12345",
        metadata={"to" + "ken": "bearer-secret-token"},
    )
    assert req.prompt_summary == "[REDACTED_SECRET]"
    assert req.metadata["token"] == "[REDACTED_SECRET]"

    dec = HumanApprovalDecision(
        approval_id="app-1",
        status=ApprovalStatus.APPROVED,
        actor="op@co.com",
        reason="Approved using " + "authorization_" + "key=secret-key",
    )
    assert dec.reason == "[REDACTED_SECRET]"


import asyncio

import pytest

from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine


class MockApprovalNotifier:
    """Mock notifier tracking outbound dispatches and verifying exception isolation."""

    def __init__(self, should_fail: bool = False) -> None:
        self.requested: list[HumanApprovalRequest] = []
        self.resolved: list[tuple[HumanApprovalRequest, HumanApprovalDecision]] = []
        self.should_fail = should_fail

    async def notify_approval_required(self, request: HumanApprovalRequest) -> bool:
        if self.should_fail:
            raise RuntimeError("Simulated network partition/timeout")
        self.requested.append(request)
        return True

    async def notify_approval_resolved(
        self, request: HumanApprovalRequest, decision: HumanApprovalDecision
    ) -> bool:
        if self.should_fail:
            raise RuntimeError("Simulated connection drop")
        self.resolved.append((request, decision))
        return True


@pytest.mark.asyncio
async def test_human_approval_engine_notifier_dispatch() -> None:
    """Test that HumanApprovalEngine dispatches notifications asynchronously upon request and resolution."""
    notifier = MockApprovalNotifier()
    engine = HumanApprovalEngine(notifier=notifier)

    binding = ActionBinding(
        session_id="sess-test",
        execution_id="exec-test",
        plan_fingerprint="fp-test",
        node_id="node-1",
        tool_id="terminal",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )
    req = HumanApprovalRequest(
        approval_id="app-test-1",
        binding=binding,
        risk_level=RiskLevel.HIGH,
        prompt_summary="Run system update script",
    )

    result_req = await engine.request_approval(req)
    assert result_req.status == ApprovalStatus.PENDING

    # Yield event loop briefly for asynchronous fire-and-forget task
    await asyncio.sleep(0.02)
    assert len(notifier.requested) == 1
    assert notifier.requested[0].approval_id == "app-test-1"

    # Submit decision (APPROVED)
    decision = HumanApprovalDecision(
        approval_id="app-test-1",
        status=ApprovalStatus.APPROVED,
        actor="security-admin@corp.internal",
        reason="Approved for scheduled maintenance",
    )
    grant = await engine.submit_decision(decision)
    assert grant.approval_id == "app-test-1"

    await asyncio.sleep(0.02)
    assert len(notifier.resolved) == 1
    assert notifier.resolved[0][1].status == ApprovalStatus.APPROVED
    assert notifier.resolved[0][1].actor == "security-admin@corp.internal"


@pytest.mark.asyncio
async def test_human_approval_engine_notifier_resilience_on_failure() -> None:
    """Test that notifier network outages or exceptions do NOT deadlock or fail HumanApprovalEngine."""
    notifier = MockApprovalNotifier(should_fail=True)
    engine = HumanApprovalEngine(notifier=notifier)

    binding = ActionBinding(
        session_id="sess-fail",
        execution_id="exec-fail",
        plan_fingerprint="fp-fail",
        node_id="node-fail",
        tool_id="system_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.SYSTEM_CONTROL}),
    )
    req = HumanApprovalRequest(
        approval_id="app-fail-1",
        binding=binding,
        risk_level=RiskLevel.CRITICAL,
        prompt_summary="Reboot server node",
    )

    # Must succeed cleanly without raising exception
    result_req = await engine.request_approval(req)
    assert result_req.status == ApprovalStatus.PENDING

    await asyncio.sleep(0.02)

    decision = HumanApprovalDecision(
        approval_id="app-fail-1",
        status=ApprovalStatus.APPROVED,
        actor="oncall@corp.internal",
        reason="Emergency approved",
    )
    # Must succeed cleanly without raising exception
    grant = await engine.submit_decision(decision)
    assert grant.approval_id == "app-fail-1"


if __name__ == "__main__":
    test_action_binding_digest_determinism()
    test_risk_evaluator_hierarchical_precedence()
    test_secret_sanitization_across_all_approval_fields()
    asyncio.run(test_human_approval_engine_notifier_dispatch())
    asyncio.run(test_human_approval_engine_notifier_resilience_on_failure())
    print("ALL P3-6 HUMAN APPROVAL UNIT TESTS PASSED SUCCESSFULLY!")
