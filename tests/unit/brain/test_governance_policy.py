"""Unit test suite for P2-5 Capability Governance, Resource Quotas, Token Grants, and Reservation Lifecycle."""

from __future__ import annotations

import asyncio
import time
import pytest

from nexusai.brain.domain.governance import (
    CapabilityGrant,
    GovernanceDecision,
    GovernanceDenialReason,
    GovernanceRequest,
    ResourceBudget,
    ResourceRequest,
    ToolCapability,
)
from nexusai.brain.runtime.governance_engine import GovernanceEngine


@pytest.mark.asyncio
async def test_A_unknown_tool_denied() -> None:
    """Test A: Requesting an unknown tool returns DENY with UNKNOWN_TOOL reason."""
    gov = GovernanceEngine()
    req = GovernanceRequest(
        execution_id="exec-1",
        node_id="node-1",
        tool_name="unregistered_tool",
        required_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        resource_request=ResourceRequest(tool_invocations=1),
    )
    decision = await gov.authorize(req)

    assert decision.allowed is False
    assert decision.reason == GovernanceDenialReason.UNKNOWN_TOOL.value


@pytest.mark.asyncio
async def test_B_missing_capability_denied() -> None:
    """Test B: Requesting capabilities not declared by tool returns DENY with CAPABILITY_MISSING reason."""
    gov = GovernanceEngine()
    req = GovernanceRequest(
        execution_id="exec-1",
        node_id="node-1",
        tool_name="file_reader",  # Only has FILE_READ capability
        required_capabilities=frozenset({ToolCapability.FILE_READ, ToolCapability.PROCESS_EXEC}),
        resource_request=ResourceRequest(tool_invocations=1),
    )
    decision = await gov.authorize(req)

    assert decision.allowed is False
    assert decision.reason == GovernanceDenialReason.CAPABILITY_MISSING.value


@pytest.mark.asyncio
async def test_C_full_capability_set_authorized() -> None:
    """Test C: Matching tool and capabilities return ALLOW decision with reservation_id."""
    gov = GovernanceEngine()
    req = GovernanceRequest(
        execution_id="exec-1",
        node_id="node-1",
        tool_name="terminal",
        required_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        resource_request=ResourceRequest(subprocesses=1, tool_invocations=1),
    )
    decision = await gov.authorize(req)

    assert decision.allowed is True
    assert decision.reservation_id is not None
    assert gov.get_active_reservation_count() == 1


@pytest.mark.asyncio
async def test_D_expired_grant_denied() -> None:
    """Test D: Expired token grant returns DENY with GRANT_EXPIRED reason."""
    gov = GovernanceEngine()
    grant = CapabilityGrant(
        execution_id="exec-1",
        tool_name="terminal",
        granted_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        expires_at=time.time() - 10.0,  # Expired 10s ago
    )
    req = GovernanceRequest(
        execution_id="exec-1",
        node_id="node-1",
        tool_name="terminal",
        required_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        resource_request=ResourceRequest(tool_invocations=1),
        grant=grant,
    )
    decision = await gov.authorize(req)

    assert decision.allowed is False
    assert decision.reason == GovernanceDenialReason.GRANT_EXPIRED.value


@pytest.mark.asyncio
async def test_E_cross_execution_grant_denied() -> None:
    """Test E: Using token grant from Execution A in Execution B returns DENY with GRANT_EXECUTION_MISMATCH."""
    gov = GovernanceEngine()
    grant = CapabilityGrant(
        execution_id="exec-A",  # Issued for Execution A
        tool_name="terminal",
        granted_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
    )
    req = GovernanceRequest(
        execution_id="exec-B",  # Requesting in Execution B
        node_id="node-1",
        tool_name="terminal",
        required_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        resource_request=ResourceRequest(tool_invocations=1),
        grant=grant,
    )
    decision = await gov.authorize(req)

    assert decision.allowed is False
    assert decision.reason == GovernanceDenialReason.GRANT_EXECUTION_MISMATCH.value


@pytest.mark.asyncio
async def test_H_atomic_reservation_all_or_nothing_failure() -> None:
    """Test H: Partial resource availability causes ALL-OR-NOTHING reservation failure (0 resources leaked)."""
    budget = ResourceBudget(max_subprocesses=2)
    gov = GovernanceEngine(global_budget=budget)

    # Reserve 2 subprocesses
    res1 = await gov.reserve("exec-1", "node-1", ResourceRequest(subprocesses=2))
    assert res1 is not None

    # Requesting 1 more subprocess exceeds capacity -> returns None
    res2 = await gov.reserve("exec-1", "node-2", ResourceRequest(subprocesses=1))
    assert res2 is None
    assert gov.get_active_reservation_count() == 1  # 0 extra resources leaked


@pytest.mark.asyncio
async def test_J_and_K_resource_release_and_double_release_safety() -> None:
    """Test J & K: Resource release restores capacity; double release returns False safely."""
    budget = ResourceBudget(max_subprocesses=1)
    gov = GovernanceEngine(global_budget=budget)

    res = await gov.reserve("exec-1", "node-1", ResourceRequest(subprocesses=1))
    assert res is not None

    # Release reservation
    released1 = await gov.release(res.reservation_id)
    assert released1 is True
    assert gov.get_active_reservation_count() == 0

    # Double release returns False safely
    released2 = await gov.release(res.reservation_id)
    assert released2 is False


@pytest.mark.asyncio
async def test_N_negative_resource_request_rejected() -> None:
    """Test N: Negative resource values in request are rejected with MALFORMED_RESOURCE_REQUEST."""
    gov = GovernanceEngine()
    req = GovernanceRequest(
        execution_id="exec-1",
        node_id="node-1",
        tool_name="terminal",
        required_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        resource_request=ResourceRequest(subprocesses=-1),
    )
    decision = await gov.authorize(req)

    assert decision.allowed is False
    assert decision.reason == GovernanceDenialReason.MALFORMED_RESOURCE_REQUEST.value


if __name__ == "__main__":
    asyncio.run(test_A_unknown_tool_denied())
    asyncio.run(test_B_missing_capability_denied())
    asyncio.run(test_C_full_capability_set_authorized())
    asyncio.run(test_D_expired_grant_denied())
    asyncio.run(test_E_cross_execution_grant_denied())
    asyncio.run(test_H_atomic_reservation_all_or_nothing_failure())
    asyncio.run(test_J_and_K_resource_release_and_double_release_safety())
    asyncio.run(test_N_negative_resource_request_rejected())
    print("ALL P2-5 GOVERNANCE POLICY UNIT TESTS PASSED SUCCESSFULLY!")
