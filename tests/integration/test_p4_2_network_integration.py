"""Integration test suite for NetworkTool governed HTTP client operations."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.ports.tool_port import ToolExecutionRequest
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.tool_registry import ToolRegistry
from nexusai.infrastructure.tools.network_tool import NetworkTool, get_network_tool_metadata


@pytest.mark.asyncio
async def test_network_integration_governed_destination_validation() -> None:
    """Verify NetworkTool enforces destination host allowlist and governance admission before HTTP dispatch."""
    net_tool = NetworkTool(allowed_hosts={"api.github.com"})
    registry = ToolRegistry()
    gov = GovernanceEngine(global_budget=ResourceBudget(max_tool_invocations=10))

    await registry.register(get_network_tool_metadata())

    # 1. Validate & Authorize NETWORK_ACCESS
    await registry.validate_tool("network_tool", requested_capabilities=frozenset({ToolCapability.NETWORK_ACCESS}))
    res_gov = await gov.authorize("exec-net-real", frozenset({ToolCapability.NETWORK_ACCESS}))
    assert res_gov.allowed is True

    # 2. Destination allowlist check for unapproved host fails closed
    req_bad = ToolExecutionRequest("exec-net-real", "network_tool", {"url": "https://unauthorized-host.org"})
    res_bad = await net_tool.execute(req_bad)
    assert res_bad.success is False
    assert "not in the network destination allowlist" in res_bad.error_message

    await gov.release(res_gov.reservation_id)
    assert gov.get_active_reservation_count() == 0


if __name__ == "__main__":
    asyncio.run(test_network_integration_governed_destination_validation())
    print("ALL P4-2 NETWORK INTEGRATION TESTS PASSED SUCCESSFULLY!")
