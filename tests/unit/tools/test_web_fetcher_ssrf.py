"""SSRF (AUDIT-09) and unbounded-response (AUDIT-14) regression tests for the Web Fetcher."""

from __future__ import annotations

import gzip
import ipaddress
from collections.abc import AsyncIterator
from unittest.mock import patch

import httpcore
import httpx
import pytest

from nexusai.tools.mcp.servers.web_fetcher import (
    ResponseTooLargeError,
    SSRFBlockedError,
    SSRFGuardNetworkBackend,
    WebFetcherMcpServer,
    build_guarded_transport,
    is_blocked_ip,
    read_limited_body,
)

PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 0))]
OK_RESPONSE = [b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\n", b"ok"]


def _resolver(mapping: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    calls: list[str] = []

    async def resolve(host: str, port: int) -> list[str]:
        calls.append(host)
        return mapping[host]

    resolve.calls = calls  # type: ignore[attr-defined]
    return resolve


@pytest.mark.parametrize(
    "addr",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.5",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "::",
        "fe80::1",
        "fd00::1",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
        "2002:7f00:1::",
        "ff02::1",
    ],
)
def test_blocked_address_ranges(addr: str) -> None:
    assert is_blocked_ip(ipaddress.ip_address(addr))


@pytest.mark.parametrize("addr", ["93.184.216.34", "8.8.8.8", "2606:4700:4700::1111"])
def test_public_addresses_allowed(addr: str) -> None:
    assert not is_blocked_ip(ipaddress.ip_address(addr))


@pytest.mark.asyncio
async def test_connect_time_validation_blocks_dns_rebinding() -> None:
    """URL validation sees a public IP, but the connection-time lookup returns loopback."""
    inner = httpcore.AsyncMockBackend(OK_RESPONSE)
    resolver = _resolver({"rebind.example": ["127.0.0.1"]})
    transport = build_guarded_transport(resolver=resolver, inner=inner)
    server = WebFetcherMcpServer(enabled=True, transport=transport)

    with patch("socket.getaddrinfo", return_value=PUBLIC_ADDRINFO):
        with pytest.raises(SSRFBlockedError, match="at connection time"):
            await server._safe_fetch("GET", "http://rebind.example/", {}, None, timeout=5)
    assert resolver.calls == ["rebind.example"]


@pytest.mark.asyncio
async def test_guard_connects_to_validated_ip_not_hostname() -> None:
    connected: list[str] = []

    class RecordingBackend(httpcore.AsyncMockBackend):
        async def connect_tcp(self, host, port, *args, **kwargs):  # type: ignore[no-untyped-def]
            connected.append(host)
            return await super().connect_tcp(host, port, *args, **kwargs)

    backend = SSRFGuardNetworkBackend(
        inner=RecordingBackend(OK_RESPONSE),
        resolver=_resolver({"example.com": ["93.184.216.34"]}),
    )
    await backend.connect_tcp("example.com", 80)
    assert connected == ["93.184.216.34"]


@pytest.mark.asyncio
async def test_guard_rejects_when_any_resolved_address_is_private() -> None:
    backend = SSRFGuardNetworkBackend(
        inner=httpcore.AsyncMockBackend(OK_RESPONSE),
        resolver=_resolver({"mixed.example": ["93.184.216.34", "10.0.0.7"]}),
    )
    with pytest.raises(SSRFBlockedError):
        await backend.connect_tcp("mixed.example", 80)


@pytest.mark.asyncio
async def test_guard_applies_to_every_pooled_connection() -> None:
    """With pooling, a second host on the same transport is still validated."""
    resolver = _resolver({"good.example": ["93.184.216.34"], "evil.example": ["169.254.169.254"]})
    transport = build_guarded_transport(
        resolver=resolver, inner=httpcore.AsyncMockBackend(OK_RESPONSE * 2)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        assert (await client.get("http://good.example/")).text == "ok"
        with pytest.raises(SSRFBlockedError):
            await client.get("http://evil.example/")


@pytest.mark.asyncio
async def test_redirect_to_metadata_endpoint_is_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data"})

    server = WebFetcherMcpServer(enabled=True, transport=httpx.MockTransport(handler))
    with patch("socket.getaddrinfo", return_value=PUBLIC_ADDRINFO):
        with pytest.raises(ValueError, match="SSRF Protection"):
            await server._safe_fetch("GET", "https://example.com/", {}, None, timeout=5)


@pytest.mark.asyncio
async def test_oversized_content_length_rejected_before_download() -> None:
    consumed: list[int] = []

    async def body() -> AsyncIterator[bytes]:
        consumed.append(1)
        yield b"x"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": str(10_000_000)}, content=body())

    server = WebFetcherMcpServer(
        enabled=True, max_response_bytes=1024, transport=httpx.MockTransport(handler)
    )
    with patch("socket.getaddrinfo", return_value=PUBLIC_ADDRINFO):
        with pytest.raises(ResponseTooLargeError):
            await server._safe_fetch("GET", "https://example.com/big", {}, None, timeout=5)
    assert consumed == []


@pytest.mark.asyncio
async def test_streaming_download_aborts_at_byte_limit() -> None:
    chunks_sent = 0

    async def endless() -> AsyncIterator[bytes]:
        nonlocal chunks_sent
        while True:
            chunks_sent += 1
            yield b"a" * 1000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=endless())

    server = WebFetcherMcpServer(
        enabled=True, max_response_bytes=5000, transport=httpx.MockTransport(handler)
    )
    with patch("socket.getaddrinfo", return_value=PUBLIC_ADDRINFO):
        _, body, truncated = await server._safe_fetch(
            "GET", "https://example.com/stream", {}, None, timeout=5
        )
    assert truncated is True
    assert len(body) == 5000
    assert chunks_sent <= 6


@pytest.mark.asyncio
async def test_decompressed_size_respects_limit() -> None:
    bomb = gzip.compress(b"\0" * 20_000_000)
    resp = httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=bomb)

    body, truncated = await read_limited_body(resp, max_bytes=64 * 1024)

    assert len(bomb) < 64 * 1024 < 20_000_000
    assert truncated is True
    assert len(body) == 64 * 1024


@pytest.mark.asyncio
async def test_fetch_url_reports_truncation_from_byte_limit() -> None:
    async def body() -> AsyncIterator[bytes]:
        for _ in range(4):
            yield b"z" * 1024

    def handler(request: httpx.Request) -> httpx.Response:
        # Streamed without Content-Length, so the limit is enforced while reading.
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=body())

    server = WebFetcherMcpServer(
        enabled=True, max_response_bytes=100, transport=httpx.MockTransport(handler)
    )
    with patch("socket.getaddrinfo", return_value=PUBLIC_ADDRINFO):
        result = await server._handle_fetch_url(
            {"url": "https://example.com/", "max_chars": 10_000}
        )
    assert result["is_truncated"] is True
    assert len(result["text"]) == 100
