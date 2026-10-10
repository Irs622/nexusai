"""Built-in Web Fetcher MCP Server providing HTTP requests and content extraction with SSRF protection."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import re
import socket
import typing
import urllib.parse
from collections.abc import Awaitable, Callable
from typing import Any

import httpcore
import httpx

from nexusai.tools.mcp.servers.base import McpServerBase

BLOCKED_HOSTNAMES = {
    "127.0.0.1",
    "localhost",
    "0.0.0.0",
    "::1",
    "169.254.169.254",
    "metadata.google.internal",
    "instance-data",
}

DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class SSRFBlockedError(ValueError):
    """Raised when a destination resolves to a forbidden (non-public) address."""


class ResponseTooLargeError(ValueError):
    """Raised when a response declares a body larger than the configured ceiling."""


def is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True for any address that is not safe to reach from the fetcher.

    Blocks loopback, RFC1918/ULA private, link-local (incl. 169.254.169.254 cloud
    metadata), CGNAT, multicast, reserved, unspecified, and every other non-global
    range. IPv4-mapped/6to4/Teredo IPv6 forms are unwrapped and checked as IPv4.
    """
    candidates: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [ip]
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            candidates.append(ip.ipv4_mapped)
        if ip.sixtofour is not None:
            candidates.append(ip.sixtofour)
        if ip.teredo is not None:
            candidates.extend(ip.teredo)
    return any(
        not c.is_global or c.is_multicast or c.is_unspecified or c.is_reserved for c in candidates
    )


Resolver = Callable[[str, int], Awaitable[list[str]]]


async def _system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.to_thread(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


class SSRFGuardNetworkBackend(httpcore.AsyncNetworkBackend):
    """httpcore network backend that validates the destination IP at connect time.

    DNS is resolved exactly once per TCP connection and the socket is opened to the
    validated IP, closing the TOCTOU window exploited by DNS rebinding. Because the
    check sits below the connection pool, it covers every hop, redirect, and new
    pooled connection. TLS still verifies the certificate against the original
    hostname (httpcore passes ``server_hostname`` separately).
    """

    def __init__(
        self,
        inner: httpcore.AsyncNetworkBackend | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        self._inner = inner or httpcore.AnyIOBackend()
        self._resolver = resolver or _system_resolver

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            addresses = await self._resolver(host, port)
        except socket.gaierror as exc:
            raise httpcore.ConnectError(f"DNS resolution failed for '{host}': {exc}") from exc
        if not addresses:
            raise httpcore.ConnectError(f"DNS resolution returned no addresses for '{host}'")
        for addr in addresses:
            if is_blocked_ip(ipaddress.ip_address(addr)):
                raise SSRFBlockedError(
                    f"SSRF Protection: Host '{host}' resolved to blocked address '{addr}' "
                    "at connection time"
                )
        last_error: Exception | None = None
        for addr in addresses:
            try:
                return await self._inner.connect_tcp(
                    addr,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout, OSError) as exc:
                last_error = exc
        raise httpcore.ConnectError(f"Could not connect to '{host}': {last_error}")

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: typing.Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise SSRFBlockedError("SSRF Protection: Unix socket connections are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def build_guarded_transport(
    resolver: Resolver | None = None,
    inner: httpcore.AsyncNetworkBackend | None = None,
) -> httpx.AsyncHTTPTransport:
    """Create an httpx transport whose every TCP connection is SSRF-validated."""
    transport = httpx.AsyncHTTPTransport(trust_env=False)
    pool = transport._pool  # httpx exposes no public hook for the network backend
    if not hasattr(pool, "_network_backend"):
        raise RuntimeError("Unsupported httpcore version: cannot install SSRF guard backend")
    pool._network_backend = SSRFGuardNetworkBackend(inner=inner, resolver=resolver)
    return transport


async def read_limited_body(resp: httpx.Response, max_bytes: int) -> tuple[bytes, bool]:
    """Read a streamed response body without exceeding ``max_bytes`` of decoded data.

    Rejects up front when ``Content-Length`` already exceeds the limit. Otherwise reads
    decompressed chunks and stops as soon as the ceiling is reached, so oversized and
    compression-bomb payloads are never fully buffered. Returns ``(body, truncated)``.
    """
    declared = resp.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise ResponseTooLargeError(
            f"Response declares {int(declared)} bytes, exceeding the {max_bytes}-byte limit"
        )
    buf = bytearray()
    async for chunk in resp.aiter_bytes():
        remaining = max_bytes - len(buf)
        if len(chunk) > remaining:
            buf.extend(chunk[:remaining])
            return bytes(buf), True
        buf.extend(chunk)
    return bytes(buf), False


def validate_ssrf_url(
    raw_url: str, allowed_hosts: set[str] | None = None
) -> urllib.parse.ParseResult:
    """Validate URL scheme and resolve target hostname against SSRF blocklists.

    Rejects:
    - Schemes other than http/https
    - Localhost, 127.0.0.0/8, 0.0.0.0, ::1
    - RFC1918 private IPv4 addresses (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - Link-local and cloud metadata addresses (169.254.0.0/16, 169.254.169.254)
    - Multicast, loopback, and reserved addresses
    """
    parsed = urllib.parse.urlparse(raw_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Network scheme '{parsed.scheme}' is not allowed (must be http or https)")

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        raise ValueError("URL must contain a valid hostname")

    if (
        hostname in BLOCKED_HOSTNAMES
        or hostname.startswith("127.")
        or hostname.startswith("169.254.")
    ):
        raise ValueError(
            f"SSRF Protection: Host '{hostname}' is blocked due to private/metadata safety policy"
        )

    # Check direct numeric or hex integer IP representations (e.g. 2130706433 or 0x7f000001)
    if hostname.isdigit() or (hostname.startswith("0x") and len(hostname) > 2):
        try:
            num_val = int(hostname, 0)
            if 0 <= num_val <= 0xFFFFFFFF:
                ip_from_num = ipaddress.IPv4Address(num_val)
                if (
                    ip_from_num.is_private
                    or ip_from_num.is_loopback
                    or ip_from_num.is_link_local
                    or ip_from_num.is_reserved
                    or ip_from_num.is_multicast
                    or str(ip_from_num) == "169.254.169.254"
                    or str(ip_from_num).startswith("0.")
                ):
                    raise ValueError(
                        f"SSRF Protection: Host '{hostname}' encoded blocked IP '{ip_from_num}'"
                    )
        except (ValueError, ipaddress.AddressValueError):
            pass

    if allowed_hosts and hostname not in allowed_hosts:
        raise ValueError(f"SSRF Protection: Host '{hostname}' is not in the destination allowlist")

    # Resolve hostname to IP addresses and inspect each address
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip_str)

            # Inspect address and its IPv4-mapped variant if applicable
            target_ips = [ip_obj]
            if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
                target_ips.append(ip_obj.ipv4_mapped)

            for target_ip in target_ips:
                if (
                    target_ip.is_private
                    or target_ip.is_loopback
                    or target_ip.is_link_local
                    or target_ip.is_reserved
                    or target_ip.is_multicast
                    or str(target_ip) == "169.254.169.254"
                    or str(target_ip).startswith("0.")
                ):
                    raise ValueError(
                        f"SSRF Protection: Host '{hostname}' resolved to blocked private/metadata IP '{target_ip}'"
                    )
    except socket.gaierror:
        pass

    return parsed


def _html_to_text(html: str) -> str:
    """Convert HTML content to clean, readable plain text without script/style tags."""
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<(p|br|div|h[1-6]|li|tr)[^>]*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    return cleaned.strip()


def _extract_title(html: str) -> str:
    """Extract <title> text from HTML if present."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


class WebFetcherMcpServer(McpServerBase):
    """MCP Server providing web fetching and generic HTTP requests with strict SSRF filtering."""

    def __init__(
        self,
        default_timeout_sec: float = 15.0,
        allowed_hosts: set[str] | None = None,
        enabled: bool = False,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            name="nexus-web-fetcher",
            version="1.0.0",
            description="NexusAI Web Fetcher & HTTP MCP Server with SSRF Protection",
        )
        self.default_timeout_sec = default_timeout_sec
        self.allowed_hosts = allowed_hosts
        self.enabled = enabled
        self.max_response_bytes = max_response_bytes
        # Tests may inject a transport; production always uses the SSRF-guarded one.
        self._transport_override = transport
        self._register_fetcher_tools()

    def _make_client(self, timeout: float) -> httpx.AsyncClient:
        transport = self._transport_override or build_guarded_transport()
        return httpx.AsyncClient(
            timeout=timeout, follow_redirects=False, transport=transport, trust_env=False
        )

    def _register_fetcher_tools(self) -> None:
        # 1. fetch_url
        self.register_tool(
            name="fetch_url",
            description="Fetch a web page via HTTP GET, convert HTML to clean readable text, and extract metadata with SSRF protection.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full HTTP or HTTPS URL to fetch",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters of text content to return (default 10,000)",
                        "default": 10000,
                    },
                },
                "required": ["url"],
            },
            handler=self._handle_fetch_url,
        )

        # 2. http_request
        self.register_tool(
            name="http_request",
            description="Perform a generic HTTP request (GET, POST, PUT, DELETE, PATCH) with SSRF protection and hop-by-hop redirect validation.",
            input_schema={
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, PUT, DELETE, PATCH)",
                        "default": "GET",
                    },
                    "url": {
                        "type": "string",
                        "description": "Full target HTTP or HTTPS URL",
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP request headers",
                        "default": {},
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional request body string for POST/PUT requests",
                        "default": "",
                    },
                    "timeout_seconds": {
                        "type": "number",
                        "description": "Request timeout in seconds",
                        "default": 15.0,
                    },
                },
                "required": ["url"],
            },
            handler=self._handle_http_request,
        )

    async def _safe_fetch(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        content: bytes | None,
        timeout: float,
        max_redirects: int = 5,
    ) -> tuple[httpx.Response, bytes, bool]:
        """Execute a request with per-hop SSRF validation and a bounded body read.

        Hostname policy (scheme, blocklist, allowlist) is checked for every hop here;
        the resolved IP is checked again at TCP connect time by the guarded transport.
        Returns ``(response, body_bytes, truncated)``.
        """
        current_url = url
        validate_ssrf_url(current_url, allowed_hosts=self.allowed_hosts)

        async with self._make_client(timeout) as client:
            for _ in range(max_redirects + 1):
                request = client.build_request(
                    method, current_url, headers=headers, content=content
                )
                resp = await client.send(request, stream=True)
                try:
                    if resp.is_redirect and method in ("GET", "HEAD"):
                        location = resp.headers.get("Location")
                        if location:
                            next_url = urllib.parse.urljoin(current_url, location)
                            validate_ssrf_url(next_url, allowed_hosts=self.allowed_hosts)
                            current_url = next_url
                            continue
                    body, truncated = await read_limited_body(resp, self.max_response_bytes)
                    return resp, body, truncated
                finally:
                    await resp.aclose()
            raise ValueError(f"Too many redirects (limit {max_redirects})")

    @staticmethod
    def _decode(resp: httpx.Response, body: bytes) -> str:
        return body.decode(resp.encoding or "utf-8", errors="replace")

    async def _handle_fetch_url(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise PermissionError(
                "WebFetcher MCP server is disabled by default. Enable it explicitly via capability profile configuration."
            )

        url = str(args["url"]).strip()
        max_chars = int(args.get("max_chars", 10000))

        # Perform initial SSRF validation
        validate_ssrf_url(url, allowed_hosts=self.allowed_hosts)

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; NexusAI-WebFetcher/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        resp, body, download_truncated = await self._safe_fetch(
            "GET", url, headers=headers, content=None, timeout=self.default_timeout_sec
        )

        content_type = resp.headers.get("content-type", "")
        raw_text = self._decode(resp, body)

        if "html" in content_type.lower():
            title = _extract_title(raw_text)
            extracted_text = _html_to_text(raw_text)
        else:
            title = ""
            extracted_text = raw_text.strip()

        truncated = len(extracted_text) > max_chars or download_truncated
        final_text = extracted_text[:max_chars]

        return {
            "url": str(resp.url),
            "status_code": resp.status_code,
            "title": title,
            "content_type": content_type,
            "text": final_text,
            "total_chars": len(extracted_text),
            "is_truncated": truncated,
        }

    async def _handle_http_request(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise PermissionError(
                "WebFetcher MCP server is disabled by default. Enable it explicitly via capability profile configuration."
            )

        method = str(args.get("method", "GET")).upper()
        url = str(args["url"]).strip()
        headers = dict(args.get("headers", {}))
        body = str(args.get("body", ""))
        timeout = float(args.get("timeout_seconds", self.default_timeout_sec))

        # Perform initial SSRF validation
        validate_ssrf_url(url, allowed_hosts=self.allowed_hosts)

        req_content = body.encode("utf-8") if body else None
        resp, resp_body, download_truncated = await self._safe_fetch(
            method, url, headers=headers, content=req_content, timeout=timeout
        )

        resp_text = self._decode(resp, resp_body)
        max_limit = 20000
        truncated = len(resp_text) > max_limit or download_truncated

        return {
            "url": str(resp.url),
            "method": method,
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": resp_text[:max_limit],
            "is_truncated": truncated,
        }


def main() -> None:
    """CLI entry point for running Web Fetcher MCP Server."""
    parser = argparse.ArgumentParser(description="NexusAI Web Fetcher & HTTP MCP Server")
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Default HTTP request timeout in seconds (default: 15.0)",
    )
    args = parser.parse_args()

    server = WebFetcherMcpServer(default_timeout_sec=args.timeout)
    server.log("Initialized Web Fetcher MCP Server with SSRF Protection")
    asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
