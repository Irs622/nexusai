"""Unit tests for NetworkTool destination host allowlist and SSRF protections."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.ports.tool_port import ToolExecutionRequest
from nexusai.infrastructure.tools.network_tool import NetworkTool


@pytest.mark.asyncio
async def test_network_tool_allowlist_and_ssrf_protections() -> None:
    """Test NetworkTool host allowlist enforcement and SSRF loopback blocking."""
    net_tool = NetworkTool(allowed_hosts={"example.com"})

    # 1. Allowed host validation passes URL parsing
    valid_req = ToolExecutionRequest("e1", "network_tool", {"url": "https://example.com"})
    # (Validation passes allowlist check)
    parsed = net_tool._validate_url("https://example.com")
    assert parsed.hostname == "example.com"

    # 2. Non-allowlisted host -> Blocked with PermissionError
    unauth_req = ToolExecutionRequest("e2", "network_tool", {"url": "https://malicious-site.com"})
    res2 = await net_tool.execute(unauth_req)
    assert res2.success is False
    assert "not in the network destination allowlist" in res2.error_message

    # 3. SSRF Loopback destination (127.0.0.1) -> Blocked with ValueError
    ssrf_req = ToolExecutionRequest("e3", "network_tool", {"url": "http://127.0.0.1:8080/admin"})
    res3 = await net_tool.execute(ssrf_req)
    assert res3.success is False
    assert "SSRF safety policy" in res3.error_message


if __name__ == "__main__":
    asyncio.run(test_network_tool_allowlist_and_ssrf_protections())
    print("ALL NETWORK TOOL UNIT TESTS PASSED SUCCESSFULLY!")
