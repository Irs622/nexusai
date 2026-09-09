"""Asynchronous HTTP and Server-Sent Events (SSE) transport for Model Context Protocol."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from nexusai.core.errors import ToolExecutionError
from nexusai.logging.logger import logger
from nexusai.tools.mcp.base import SseEvent


class McpHttpTransport:
    """Manages asynchronous HTTP connection pooling and SSE streaming for remote MCP communication."""

    def __init__(
        self,
        base_headers: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
        max_connections: int = 50,
        max_keepalive_connections: int = 20,
    ) -> None:
        self.base_headers = base_headers or {}
        self.timeout_seconds = timeout_seconds

        limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=30.0,
        )
        timeout = httpx.Timeout(
            timeout_seconds,
            connect=10.0,
            read=None,  # Do not timeout on long-lived SSE read streams
            write=15.0,
            pool=10.0,
        )

        self._client: httpx.AsyncClient | None = httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            headers={
                "User-Agent": "NexusAI-MCP-Client/1.0.0",
                **self.base_headers,
            },
            follow_redirects=True,
        )

    @property
    def client(self) -> httpx.AsyncClient:
        """Return active httpx.AsyncClient instance or raise error if closed."""
        if self._client is None or self._client.is_closed:
            raise ToolExecutionError("McpHttpTransport is not running or has been closed")
        return self._client

    async def __aenter__(self) -> McpHttpTransport:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close underlying HTTP client and release connection pool."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.debug("[McpHttpTransport] HTTP client connection pool closed")

    async def stream_sse(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> AsyncIterator[SseEvent]:
        """Connect to an SSE endpoint and yield structured SseEvent objects conforming to W3C specification.

        Args:
            url: The remote SSE endpoint URL.
            headers: Optional request headers to merge with base headers.

        Yields:
            Parsed SseEvent instances.
        """
        req_headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            **(headers or {}),
        }

        try:
            async with self.client.stream("GET", url, headers=req_headers) as response:
                if response.status_code != 200:
                    raise ToolExecutionError(
                        f"SSE endpoint '{url}' returned non-200 HTTP status: {response.status_code}"
                    )

                event_type = "message"
                data_lines: list[str] = []
                event_id: str | None = None
                retry_ms: int | None = None

                async for raw_line in response.aiter_lines():
                    line = raw_line.rstrip("\r\n")

                    # Empty line dispatches the buffered event frame
                    if not line:
                        if data_lines or event_type == "endpoint":
                            yield SseEvent(
                                event=event_type,
                                data="\n".join(data_lines),
                                id=event_id,
                                retry=retry_ms,
                            )
                            event_type = "message"
                            data_lines = []
                            event_id = None
                        continue

                    # Ignore SSE comment / keepalive ping lines (starting with ':')
                    if line.startswith(":"):
                        continue

                    # Parse field and value
                    if ":" in line:
                        field, value = line.split(":", 1)
                        if value.startswith(" "):
                            value = value[1:]
                    else:
                        field, value = line, ""

                    if field == "event":
                        event_type = value
                    elif field == "data":
                        data_lines.append(value)
                    elif field == "id":
                        event_id = value
                    elif field == "retry":
                        try:
                            retry_ms = int(value)
                        except ValueError:
                            pass

                # Flush any residual buffered event at end of stream
                if data_lines or event_type == "endpoint":
                    yield SseEvent(
                        event=event_type,
                        data="\n".join(data_lines),
                        id=event_id,
                        retry=retry_ms,
                    )

        except (httpx.TransportError, httpx.HTTPStatusError) as net_err:
            raise ToolExecutionError(
                f"Network transport error while streaming SSE from '{url}': {net_err}"
            ) from net_err

    async def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any] | None, str]:
        """Send a JSON payload via HTTP POST.

        Args:
            url: Target endpoint URL.
            payload: JSON-serializable dictionary.
            headers: Optional request headers.

        Returns:
            Tuple of (status_code, json_dict_or_none, response_text).
        """
        req_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            **(headers or {}),
        }

        try:
            response = await self.client.post(
                url,
                json=payload,
                headers=req_headers,
                timeout=self.timeout_seconds,
            )
            parsed_json: dict[str, Any] | None = None
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        parsed_json = data
                except Exception:
                    parsed_json = None

            return response.status_code, parsed_json, response.text

        except (httpx.TransportError, httpx.TimeoutException) as err:
            raise ToolExecutionError(f"HTTP POST request to '{url}' failed: {err}") from err
