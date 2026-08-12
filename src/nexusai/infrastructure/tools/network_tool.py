"""Governed NetworkTool adapter enforcing host allowlists, scheme validation, SSRF protection, and redirect policies."""

from __future__ import annotations

import urllib.parse
import urllib.request
from typing import Any

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.tool_registry import ToolMetadata, ToolStatus, ToolTrustLevel
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult


class NetworkTool(IToolPort):
    """Real network HTTP client adapter enforcing destination host allowlists, SSRF protections, and response size limits."""

    def __init__(
        self,
        allowed_hosts: set[str] | None = None,
        default_timeout_seconds: float = 5.0,
        max_response_bytes: int = 1024 * 1024,  # 1 MB limit
    ) -> None:
        self.allowed_hosts = allowed_hosts or {"api.github.com", "httpbin.org", "example.com"}
        self.default_timeout_seconds = default_timeout_seconds
        self.max_response_bytes = max_response_bytes

        # Block loopback / metadata service addresses to prevent SSRF
        self.blocked_hosts = {"127.0.0.1", "localhost", "0.0.0.0", "169.254.169.254", "::1"}

    def _validate_url(self, raw_url: str) -> urllib.parse.ParseResult:
        """Validate URL scheme and host against destination allowlist and SSRF blocklist."""
        parsed = urllib.parse.urlparse(raw_url)

        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Network scheme '{parsed.scheme}' is not allowed (must be http or https)")

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise ValueError("URL must contain a valid hostname")

        if hostname in self.blocked_hosts or hostname.startswith("127.") or hostname.startswith("192.168."):
            raise ValueError(f"Host '{hostname}' is blocked due to SSRF safety policy")

        if self.allowed_hosts and hostname not in self.allowed_hosts:
            raise PermissionError(f"Host '{hostname}' is not in the network destination allowlist")

        return parsed

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Execute governed HTTP GET/POST request with destination validation."""
        raw_url = request.parameters.get("url", "")
        method = request.parameters.get("method", "GET").upper()

        if not raw_url:
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=False,
                error_message="Parameter 'url' is required",
            )

        try:
            self._validate_url(raw_url)

            timeout = float(request.parameters.get("timeout", self.default_timeout_seconds))
            req = urllib.request.Request(raw_url, method=method)
            req.add_header("User-Agent", "NexusAI-Governed-Runtime/0.7.0")

            # Execute HTTP request using standard urllib with timeout
            with urllib.request.urlopen(req, timeout=timeout) as response:
                # Redirect policy check: Ensure final redirected URL is also in allowlist!
                final_url = response.geturl()
                self._validate_url(final_url)

                data = response.read(self.max_response_bytes)
                output_str = data.decode("utf-8", errors="replace")

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
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=False,
                error_message=f"Network request error: {err}",
            )


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
