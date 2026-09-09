"""Asynchronous Model Context Protocol (MCP) Client using Server-Sent Events (SSE) and HTTP streaming."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urljoin

from nexusai.core.errors import ToolExecutionError
from nexusai.logging.logger import logger
from nexusai.tools.mcp.base import BaseMcpClient
from nexusai.tools.mcp.models import (
    JsonRpcRequest,
    JsonRpcResponse,
    McpCallToolResult,
    McpPromptDefinition,
    McpResourceDefinition,
    McpServerConfig,
    McpToolContent,
    McpToolDefinition,
)
from nexusai.tools.mcp.transport import McpHttpTransport


class McpSseClient(BaseMcpClient):
    """Asynchronous client managing Server-Sent Events (SSE) and HTTP streaming for remote MCP servers."""

    def __init__(self, config: McpServerConfig) -> None:
        self.config = config
        self._transport: McpHttpTransport | None = None
        self._sse_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._endpoint_ready_event = asyncio.Event()

        self._post_url: str | None = None
        self._pending_requests: dict[int | str, asyncio.Future[JsonRpcResponse]] = {}
        self._request_counter = 0

        self._lock = asyncio.Lock()
        self._is_connected = False
        self._is_initialized = False
        self._is_closing = False
        self._server_info: dict[str, Any] = {}
        self._reconnect_attempts = 0

    @property
    def is_connected(self) -> bool:
        """Return True if SSE connection is active and protocol handshake succeeded."""
        return self._is_connected and self._is_initialized

    @property
    def server_name(self) -> str:
        """Return identifier name for this server."""
        return self.config.name

    @property
    def post_url(self) -> str | None:
        """Return resolved HTTP POST endpoint for client messages."""
        return self._post_url

    async def start(self) -> None:
        """Establish SSE connection, discover message endpoint, and complete MCP handshake."""
        async with self._lock:
            if self.is_connected:
                return

            if not self.config.url:
                raise ToolExecutionError(
                    f"Remote MCP server '{self.config.name}' requires a valid endpoint URL"
                )

            self._is_closing = False
            self._endpoint_ready_event.clear()

            # Initialize HTTP transport with connection pooling
            self._transport = McpHttpTransport(
                base_headers=self.config.headers,
                timeout_seconds=self.config.timeout_seconds,
            )

            # Spawn background SSE reader task
            self._sse_task = asyncio.create_task(self._sse_listener_loop())

            # Await endpoint discovery event (or fallback to configured url)
            try:
                await asyncio.wait_for(
                    self._endpoint_ready_event.wait(),
                    timeout=min(self.config.timeout_seconds, 10.0),
                )
            except asyncio.TimeoutError:
                if not self._post_url:
                    logger.debug(
                        f"[McpSseClient:{self.config.name}] No 'endpoint' event received; defaulting to base URL: {self.config.url}"
                    )
                    self._post_url = self.config.url

            # Execute MCP Handshake ('initialize' -> 'notifications/initialized')
            try:
                init_res = await asyncio.wait_for(
                    self._send_request(
                        "initialize",
                        {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "NexusAI", "version": "1.0.0"},
                        },
                    ),
                    timeout=self.config.timeout_seconds,
                )

                if init_res.error:
                    raise ToolExecutionError(
                        f"MCP initialization rejected by '{self.config.name}': {init_res.error.message}"
                    )

                self._server_info = init_res.result or {}

                # Send initialized notification
                await self._send_notification("notifications/initialized", {})

                self._is_connected = True
                self._is_initialized = True
                self._reconnect_attempts = 0

                # Launch periodic heartbeat task if configured
                if self.config.heartbeat_interval_seconds > 0:
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                logger.info(
                    f"[McpSseClient:{self.config.name}] Successfully connected and initialized via SSE: {self.config.url}"
                )

            except Exception as e:
                await self.stop()
                raise ToolExecutionError(
                    f"MCP SSE initialization failed for '{self.config.name}': {e}"
                ) from e

    async def stop(self) -> None:
        """Gracefully disconnect SSE stream, cancel pending requests, and close connection pool."""
        self._is_closing = True
        self._is_connected = False
        self._is_initialized = False

        # Cancel heartbeat task
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        # Fail any pending futures with cancellation
        for req_id, fut in list(self._pending_requests.items()):
            if not fut.done():
                fut.cancel()
        self._pending_requests.clear()

        # Cancel SSE listener task
        if self._sse_task and not self._sse_task.done():
            self._sse_task.cancel()
            try:
                await self._sse_task
            except (asyncio.CancelledError, Exception):
                pass
            self._sse_task = None

        # Close transport pool
        if self._transport:
            await self._transport.close()
            self._transport = None

        logger.info(f"[McpSseClient:{self.config.name}] Stopped and disconnected")

    async def list_tools(self) -> list[McpToolDefinition]:
        """Fetch list of available tools declared by remote MCP server."""
        if not self.is_connected:
            raise ToolExecutionError(f"MCP server '{self.config.name}' is not connected")

        response = await self._send_request("tools/list", {})
        if response.error:
            raise ToolExecutionError(
                f"Failed to list tools from '{self.config.name}': {response.error.message}"
            )

        tools_data = (response.result or {}).get("tools", [])
        definitions: list[McpToolDefinition] = []
        for item in tools_data:
            try:
                definitions.append(McpToolDefinition.model_validate(item))
            except Exception as e:
                logger.warning(
                    f"[McpSseClient:{self.config.name}] Skipping malformed tool definition: {item} ({e})"
                )
        return definitions

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> McpCallToolResult:
        """Execute a tool via tools/call request."""
        if not self.is_connected:
            raise ToolExecutionError(f"MCP server '{self.config.name}' is not connected")

        response = await self._send_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )

        if response.error:
            raise ToolExecutionError(
                f"MCP tool '{tool_name}' failed on '{self.config.name}': {response.error.message}"
            )

        result_data = response.result or {}
        try:
            return McpCallToolResult.model_validate(result_data)
        except Exception as e:
            raise ToolExecutionError(
                f"Malformed tool call response from '{self.config.name}' for tool '{tool_name}': {e}"
            ) from e

    async def stream_tool_call(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> AsyncIterator[McpToolContent]:
        """Execute tool and stream content chunks asynchronously without blocking event loop."""
        result = await self.call_tool(tool_name, arguments)
        for item in result.content:
            yield item
            # Yield control back to event loop for true cooperative multitasking
            await asyncio.sleep(0)

    async def list_prompts(self) -> list[McpPromptDefinition]:
        """Fetch list of available prompt templates from remote server."""
        if not self.is_connected:
            raise ToolExecutionError(f"MCP server '{self.config.name}' is not connected")

        response = await self._send_request("prompts/list", {})
        if response.error:
            raise ToolExecutionError(
                f"Failed to list prompts from '{self.config.name}': {response.error.message}"
            )

        prompts_data = (response.result or {}).get("prompts", [])
        definitions: list[McpPromptDefinition] = []
        for item in prompts_data:
            try:
                definitions.append(McpPromptDefinition.model_validate(item))
            except Exception as e:
                logger.warning(
                    f"[McpSseClient:{self.config.name}] Skipping malformed prompt definition: {item} ({e})"
                )
        return definitions

    async def list_resources(self) -> list[McpResourceDefinition]:
        """Fetch list of available resources from remote server."""
        if not self.is_connected:
            raise ToolExecutionError(f"MCP server '{self.config.name}' is not connected")

        response = await self._send_request("resources/list", {})
        if response.error:
            raise ToolExecutionError(
                f"Failed to list resources from '{self.config.name}': {response.error.message}"
            )

        resources_data = (response.result or {}).get("resources", [])
        definitions: list[McpResourceDefinition] = []
        for item in resources_data:
            try:
                definitions.append(McpResourceDefinition.model_validate(item))
            except Exception as e:
                logger.warning(
                    f"[McpSseClient:{self.config.name}] Skipping malformed resource definition: {item} ({e})"
                )
        return definitions

    async def ping(self) -> bool:
        """Send ping request to check server responsiveness."""
        if not self._is_connected or not self._transport:
            return False
        try:
            res = await self._send_request("ping", {})
            return res.error is None
        except Exception:
            return False

    async def _send_request(self, method: str, params: dict[str, Any]) -> JsonRpcResponse:
        """Send a JSON-RPC 2.0 request via HTTP POST and await response matched by correlation ID."""
        if not self._transport:
            raise ToolExecutionError(f"Transport for '{self.config.name}' is not available")

        target_url = self._post_url or self.config.url
        if not target_url:
            raise ToolExecutionError(
                f"Target POST endpoint URL for '{self.config.name}' has not been resolved"
            )

        self._request_counter += 1
        req_id = self._request_counter

        request = JsonRpcRequest(id=req_id, method=method, params=params)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[JsonRpcResponse] = loop.create_future()
        self._pending_requests[req_id] = future

        try:
            status_code, response_json, raw_text = await self._transport.post_json(
                target_url, request.model_dump(exclude_none=True)
            )

            if status_code >= 400:
                self._pending_requests.pop(req_id, None)
                raise ToolExecutionError(
                    f"HTTP error {status_code} sending request '{method}' to '{self.config.name}': {raw_text}"
                )

            # Direct HTTP JSON-RPC response optimization
            if response_json and (
                response_json.get("id") == req_id
                or "result" in response_json
                or "error" in response_json
            ):
                self._pending_requests.pop(req_id, None)
                return JsonRpcResponse.model_validate(response_json)

        except Exception as e:
            self._pending_requests.pop(req_id, None)
            raise ToolExecutionError(
                f"Failed to dispatch request '{method}' to '{self.config.name}': {e}"
            ) from e

        # Otherwise wait for response over the SSE stream
        try:
            return await asyncio.wait_for(future, timeout=self.config.timeout_seconds)
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            raise ToolExecutionError(
                f"Timeout waiting for SSE response from '{self.config.name}' for method '{method}'"
            )

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a fire-and-forget JSON-RPC 2.0 notification via HTTP POST."""
        if not self._transport:
            return

        target_url = self._post_url or self.config.url
        if not target_url:
            return

        notification = JsonRpcRequest(id=None, method=method, params=params)
        try:
            await self._transport.post_json(target_url, notification.model_dump(exclude_none=True))
        except Exception as e:
            logger.warning(
                f"[McpSseClient:{self.config.name}] Failed to send notification '{method}': {e}"
            )

    async def _sse_listener_loop(self) -> None:
        """Continuously consume and dispatch events from the remote SSE stream."""
        while not self._is_closing:
            if not self._transport or not self.config.url:
                break

            try:
                async for event in self._transport.stream_sse(self.config.url):
                    if self._is_closing:
                        break

                    # 1. MCP Endpoint declaration event
                    if event.event == "endpoint":
                        raw_endpoint = event.data.strip()
                        self._post_url = urljoin(self.config.url, raw_endpoint)
                        self._endpoint_ready_event.set()
                        logger.debug(
                            f"[McpSseClient:{self.config.name}] Resolved POST endpoint: {self._post_url}"
                        )
                        continue

                    # 2. JSON-RPC Message event
                    if event.event == "message" and event.data:
                        try:
                            payload = json.loads(event.data)
                        except json.JSONDecodeError:
                            logger.debug(
                                f"[McpSseClient:{self.config.name}] Malformed JSON event data: {event.data}"
                            )
                            continue

                        req_id = payload.get("id")
                        if req_id is not None and req_id in self._pending_requests:
                            future = self._pending_requests.pop(req_id)
                            if not future.done():
                                try:
                                    response = JsonRpcResponse.model_validate(payload)
                                    future.set_result(response)
                                except Exception as val_err:
                                    future.set_exception(val_err)

            except asyncio.CancelledError:
                break
            except Exception as stream_err:
                logger.warning(
                    f"[McpSseClient:{self.config.name}] SSE connection dropped: {stream_err}"
                )

            # If dropped unintentionally while initialized, initiate automatic reconnect
            if not self._is_closing and self._is_initialized:
                self._is_connected = False
                await self._trigger_reconnect()
                if self._is_connected:
                    continue
            break

    async def _trigger_reconnect(self) -> None:
        """Attempt automatic reconnection with exponential backoff."""
        while self._reconnect_attempts < self.config.reconnect_retries and not self._is_closing:
            self._reconnect_attempts += 1
            backoff = min(
                self.config.reconnect_backoff_seconds * (2 ** (self._reconnect_attempts - 1)),
                self.config.reconnect_max_backoff_seconds,
            )
            logger.info(
                f"[McpSseClient:{self.config.name}] Reconnecting in {backoff:.1f}s (attempt {self._reconnect_attempts}/{self.config.reconnect_retries})..."
            )
            await asyncio.sleep(backoff)

            if self._is_closing:
                break

            try:
                # Refresh HTTP transport if needed
                if self._transport:
                    await self._transport.close()
                self._transport = McpHttpTransport(
                    base_headers=self.config.headers,
                    timeout_seconds=self.config.timeout_seconds,
                )

                # Send a test ping or handshake
                is_responsive = await self.ping()
                if is_responsive or not self._is_closing:
                    self._is_connected = True
                    self._reconnect_attempts = 0
                    logger.info(
                        f"[McpSseClient:{self.config.name}] Successfully reconnected to remote MCP server"
                    )
                    return
            except Exception as rec_err:
                logger.debug(
                    f"[McpSseClient:{self.config.name}] Reconnect attempt {self._reconnect_attempts} failed: {rec_err}"
                )

        if not self._is_closing:
            logger.error(
                f"[McpSseClient:{self.config.name}] Exhausted all {self.config.reconnect_retries} reconnect attempts. Marking client offline."
            )
            # Fail all pending futures with connection error
            err = ToolExecutionError(
                f"Connection to remote MCP server '{self.config.name}' was lost and could not be recovered"
            )
            for fut in list(self._pending_requests.values()):
                if not fut.done():
                    fut.set_exception(err)
            self._pending_requests.clear()

    async def _heartbeat_loop(self) -> None:
        """Periodic background task verifying server liveliness."""
        while not self._is_closing and self._is_connected:
            try:
                await asyncio.sleep(self.config.heartbeat_interval_seconds)
                if self._is_closing or not self._is_connected:
                    break

                is_alive = await self.ping()
                if not is_alive:
                    logger.warning(
                        f"[McpSseClient:{self.config.name}] Heartbeat ping failed. Triggering recovery."
                    )
                    self._is_connected = False
                    await self._trigger_reconnect()
            except asyncio.CancelledError:
                break
            except Exception as hb_err:
                logger.debug(
                    f"[McpSseClient:{self.config.name}] Exception in heartbeat loop: {hb_err}"
                )
