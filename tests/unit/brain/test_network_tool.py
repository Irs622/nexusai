"""Unit tests for NetworkTool destination host allowlist and SSRF protections."""

from __future__ import annotations

import asyncio
import email.message
import socket
import urllib.error
from typing import Any

import pytest

from nexusai.brain.ports.tool_port import ToolExecutionRequest
from nexusai.infrastructure.tools import network_tool as network_tool_module
from nexusai.infrastructure.tools.network_tool import (
    BlockedDestinationError,
    NetworkTool,
    _guarded_create_connection,
)


@pytest.mark.asyncio
async def test_network_tool_allowlist_and_ssrf_protections() -> None:
    """Test NetworkTool host allowlist enforcement and SSRF loopback blocking."""
    net_tool = NetworkTool(allowed_hosts={"example.com"})

    # 1. Allowed host validation passes URL parsing
    ToolExecutionRequest(
        tool_name="network_tool", arguments={"url": "https://example.com"}, execution_id="e1"
    )
    # (Validation passes allowlist check)
    parsed = net_tool._validate_url("https://example.com")
    assert parsed.hostname == "example.com"

    # 2. Non-allowlisted host -> Blocked with PermissionError
    unauth_req = ToolExecutionRequest(
        tool_name="network_tool", arguments={"url": "https://malicious-site.com"}, execution_id="e2"
    )
    res2 = await net_tool.execute(unauth_req)
    assert res2.success is False
    assert res2.error_message is not None
    assert "not in the network destination allowlist" in res2.error_message

    # 3. SSRF Loopback destination (127.0.0.1) -> Blocked with ValueError
    ssrf_req = ToolExecutionRequest(
        tool_name="network_tool",
        arguments={"url": "http://127.0.0.1:8080/admin"},
        execution_id="e3",
    )
    res3 = await net_tool.execute(ssrf_req)
    assert res3.success is False
    assert res3.error_message is not None
    assert "SSRF safety policy" in res3.error_message


def _public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve every hostname to a public address so tests never touch real DNS."""

    def fake_getaddrinfo(host: str, *args: Any, **kwargs: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(network_tool_module.socket, "getaddrinfo", fake_getaddrinfo)


@pytest.mark.asyncio
async def test_redirect_to_metadata_service_is_never_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A redirect hop is validated before it is requested, so internal targets are never hit."""
    _public_dns(monkeypatch)
    net_tool = NetworkTool(allowed_hosts={"example.com"})
    requested: list[str] = []

    def fake_open(req: Any, timeout: float) -> Any:
        requested.append(req.full_url)
        headers = email.message.Message()
        headers["Location"] = "http://169.254.169.254/latest/meta-data/"
        raise urllib.error.HTTPError(req.full_url, 302, "Found", headers, None)

    monkeypatch.setattr(net_tool._opener, "open", fake_open)

    res = await net_tool.execute(
        ToolExecutionRequest(
            tool_name="network_tool", arguments={"url": "https://example.com/"}, execution_id="r1"
        )
    )

    assert res.success is False
    assert "SSRF safety policy" in (res.error_message or "")
    assert requested == ["https://example.com/"]


def test_guarded_connection_rejects_loopback_peer() -> None:
    """The connected peer is checked, which defeats DNS rebinding to internal addresses."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        with pytest.raises(BlockedDestinationError):
            _guarded_create_connection(("127.0.0.1", server.getsockname()[1]), 2.0)
    finally:
        server.close()


if __name__ == "__main__":
    asyncio.run(test_network_tool_allowlist_and_ssrf_protections())
    print("ALL NETWORK TOOL UNIT TESTS PASSED SUCCESSFULLY!")
