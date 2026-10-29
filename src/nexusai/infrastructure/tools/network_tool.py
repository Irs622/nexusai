"""Governed NetworkTool adapter enforcing host allowlists, scheme validation, SSRF protection, and redirect policies."""

from __future__ import annotations

import asyncio
import http.client
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.tool_registry import ToolMetadata, ToolStatus, ToolTrustLevel
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.logging.logger import logger


_REDIRECT_CODES = (301, 302, 303, 307, 308)


class BlockedDestinationError(ValueError):
    """Raised when a connection would reach a private, loopback or otherwise blocked address."""


def _is_blocked_ip(ip_str: str) -> bool:
    """Return True for addresses that must never be reached (SSRF protection)."""
    ip_obj = ipaddress.ip_address(ip_str.split("%", 1)[0])
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
        ip_obj = ip_obj.ipv4_mapped
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_reserved
        or ip_obj.is_multicast
        or ip_obj.is_unspecified
    )


def _guarded_create_connection(
    address: tuple[str, int], timeout: Any, source_address: Any = None, **kwargs: Any
) -> socket.socket:
    """Open a TCP connection and verify the address actually connected to.

    Checking the connected peer (rather than a separate DNS lookup) closes the DNS-rebinding
    gap between validation and connection.
    """
    sock = socket.create_connection(address, timeout, source_address, **kwargs)
    peer_ip = sock.getpeername()[0]
    if _is_blocked_ip(peer_ip):
        sock.close()
        raise BlockedDestinationError(
            f"Host '{address[0]}' connected to private/blocked IP '{peer_ip}' (SSRF safety policy)"
        )
    return sock


class _GuardedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._create_connection = _guarded_create_connection


class _GuardedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._create_connection = _guarded_create_connection


class _GuardedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(_GuardedHTTPConnection, req)  # type: ignore[arg-type]


class _GuardedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(  # type: ignore[arg-type]
            _GuardedHTTPSConnection,
            req,
            context=self._context,  # type: ignore[attr-defined]
        )


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Surface redirects as HTTPError so every hop can be validated before it is requested."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _build_guarded_opener() -> urllib.request.OpenerDirector:
    # Environment proxies are disabled: through a proxy the connected peer is the proxy,
    # which would defeat the peer-address check.
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _GuardedHTTPHandler(),
        _GuardedHTTPSHandler(),
        _NoRedirectHandler(),
    )


class NetworkTool(IToolPort):
    """Real network HTTP client adapter enforcing destination host allowlists, SSRF protections, and response size limits."""

    def __init__(
        self,
        allowed_hosts: set[str] | None = None,
        default_timeout_seconds: float = 5.0,
        max_response_bytes: int = 1024 * 1024,  # 1 MB limit
        max_redirects: int = 5,
    ) -> None:
        self.allowed_hosts = allowed_hosts or {"api.github.com", "httpbin.org", "example.com"}
        self.default_timeout_seconds = default_timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_redirects = max_redirects
        self._opener = _build_guarded_opener()

        # Block loopback / metadata service addresses to prevent SSRF
        self.blocked_hosts = {"127.0.0.1", "localhost", "0.0.0.0", "169.254.169.254", "::1"}

    def _validate_url(self, raw_url: str) -> urllib.parse.ParseResult:
        """Validate URL scheme, hostname allowlist, and resolve IP addresses against SSRF blocklists."""
        parsed = urllib.parse.urlparse(raw_url)

        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"Network scheme '{parsed.scheme}' is not allowed (must be http or https)"
            )

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise ValueError("URL must contain a valid hostname")

        if (
            hostname in self.blocked_hosts
            or hostname.startswith("127.")
            or hostname.startswith("192.168.")
        ):
            raise ValueError(f"Host '{hostname}' is blocked due to SSRF safety policy")

        if self.allowed_hosts and hostname not in self.allowed_hosts:
            raise PermissionError(f"Host '{hostname}' is not in the network destination allowlist")

        # Early rejection of hosts resolving to private / link-local / loopback / reserved IP
        # ranges. This is a fast path only: the authoritative check is made on the connected
        # socket in _guarded_create_connection, which also covers DNS rebinding.
        try:
            addr_info = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            addr_info = []  # Unresolvable hosts cannot be connected to; the request fails later.
        for _, _, _, _, sockaddr in addr_info:
            ip_str = str(sockaddr[0])
            if _is_blocked_ip(ip_str):
                raise ValueError(
                    f"Host '{hostname}' resolved to private/blocked IP '{ip_str}' (SSRF protection)"
                )

        return parsed

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Execute governed HTTP GET/POST request with destination validation."""
        params = (
            request.parameters
            if isinstance(request.parameters, dict)
            else request.arguments
            if isinstance(request.arguments, dict)
            else {}
        )
        raw_url = params.get("url", "")
        method = params.get("method", "GET").upper()

        if not raw_url:
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=False,
                error_message="Parameter 'url' is required",
            )

        try:
            timeout = float(params.get("timeout", self.default_timeout_seconds))
            output_str = await asyncio.to_thread(self._fetch, raw_url, method, timeout)
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=True,
                output=output_str,
            )

        except (ValueError, PermissionError) as err:
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=False,
                error_message=str(err),
            )
        except Exception as err:
            logger.warning("network_tool: suppressed exception: {!r}", err)
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=False,
                error_message=f"Network request error: {err}",
            )

    def _fetch(self, raw_url: str, method: str, timeout: float) -> str:
        """Perform the request, validating every redirect hop before it is requested."""
        url = raw_url
        for _ in range(self.max_redirects + 1):
            self._validate_url(url)
            req = urllib.request.Request(url, method=method)
            req.add_header("User-Agent", "NexusAI-Governed-Runtime/0.7.0")
            try:
                with self._opener.open(req, timeout=timeout) as response:
                    data = response.read(self.max_response_bytes)
                    return str(data.decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as err:
                location = err.headers.get("Location") if err.code in _REDIRECT_CODES else None
                if not location:
                    raise
                err.close()
                url = urllib.parse.urljoin(url, location)
                if err.code == 303 or (err.code in (301, 302) and method not in ("GET", "HEAD")):
                    method = "GET"
        raise ValueError(f"Too many redirects (limit {self.max_redirects})")


def get_network_tool_metadata() -> ToolMetadata:
    """Return ToolMetadata for NetworkTool."""
    return ToolMetadata(
        tool_id="network_tool",
        name="Network HTTP Tool",
        version="1.0.0",
        description="Governed HTTP client with destination allowlists",
        capabilities=frozenset({ToolCapability.NETWORK_ACCESS}),
        status=ToolStatus.ENABLED,
        trust_level=ToolTrustLevel.VERIFIED,
    )
