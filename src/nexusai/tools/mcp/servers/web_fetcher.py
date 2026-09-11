"""Built-in Web Fetcher MCP Server providing HTTP requests and content extraction with SSRF protection."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import re
import socket
import urllib.parse
from typing import Any

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
        enabled: bool = True,
    ) -> None:
        super().__init__(
            name="nexus-web-fetcher",
            version="1.0.0",
            description="NexusAI Web Fetcher & HTTP MCP Server with SSRF Protection",
        )
        self.default_timeout_sec = default_timeout_sec
        self.allowed_hosts = allowed_hosts
        self.enabled = enabled
        self._register_fetcher_tools()

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

    async def _safe_http_get(
        self,
        url: str,
        headers: dict[str, str],
        timeout: float,
        max_redirects: int = 5,
    ) -> httpx.Response:
        """Execute HTTP GET with hop-by-hop SSRF validation on redirects."""
        current_url = url
        validate_ssrf_url(current_url, allowed_hosts=self.allowed_hosts)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for _ in range(max_redirects + 1):
                resp = await client.get(current_url, headers=headers)
                if resp.is_redirect:
                    location = resp.headers.get("Location")
                    if not location:
                        return resp
                    next_url = urllib.parse.urljoin(current_url, location)
                    validate_ssrf_url(next_url, allowed_hosts=self.allowed_hosts)
                    current_url = next_url
                else:
                    return resp
            raise ValueError(f"Too many redirects (limit {max_redirects})")

    async def _safe_http_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        content: bytes | None,
        timeout: float,
        max_redirects: int = 5,
    ) -> httpx.Response:
        """Execute HTTP request with hop-by-hop SSRF validation on redirects."""
        current_url = url
        validate_ssrf_url(current_url, allowed_hosts=self.allowed_hosts)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for _ in range(max_redirects + 1):
                resp = await client.request(method, current_url, headers=headers, content=content)
                if resp.is_redirect and method in ("GET", "HEAD"):
                    location = resp.headers.get("Location")
                    if not location:
                        return resp
                    next_url = urllib.parse.urljoin(current_url, location)
                    validate_ssrf_url(next_url, allowed_hosts=self.allowed_hosts)
                    current_url = next_url
                else:
                    return resp
            raise ValueError(f"Too many redirects (limit {max_redirects})")

    async def _handle_fetch_url(self, args: dict[str, Any]) -> dict[str, Any]:
        url = str(args["url"]).strip()
        max_chars = int(args.get("max_chars", 10000))

        # Perform initial SSRF validation
        validate_ssrf_url(url, allowed_hosts=self.allowed_hosts)

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; NexusAI-WebFetcher/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        resp = await self._safe_http_get(url, headers=headers, timeout=self.default_timeout_sec)

        content_type = resp.headers.get("content-type", "")
        raw_text = resp.text

        if "html" in content_type.lower():
            title = _extract_title(raw_text)
            extracted_text = _html_to_text(raw_text)
        else:
            title = ""
            extracted_text = raw_text.strip()

        truncated = len(extracted_text) > max_chars
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
        method = str(args.get("method", "GET")).upper()
        url = str(args["url"]).strip()
        headers = dict(args.get("headers", {}))
        body = str(args.get("body", ""))
        timeout = float(args.get("timeout_seconds", self.default_timeout_sec))

        # Perform initial SSRF validation
        validate_ssrf_url(url, allowed_hosts=self.allowed_hosts)

        req_content = body.encode("utf-8") if body else None
        resp = await self._safe_http_request(
            method, url, headers=headers, content=req_content, timeout=timeout
        )

        resp_text = resp.text
        max_limit = 20000
        truncated = len(resp_text) > max_limit

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
