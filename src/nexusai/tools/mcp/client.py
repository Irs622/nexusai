"""Asynchronous Model Context Protocol (MCP) Client using Stdio JSON-RPC 2.0 transport."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from nexusai.core.errors import ToolExecutionError
from nexusai.logging.logger import logger
from nexusai.tools.mcp.models import (
    JsonRpcRequest,
    JsonRpcResponse,
    McpCallToolResult,
    McpServerConfig,
    McpToolDefinition,
)


class McpClient:
    """Asynchronous client managing standard I/O (stdio) transport to an external MCP process."""

    def __init__(self, config: McpServerConfig) -> None:
        self.config = config
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._pending_requests: dict[int | str, asyncio.Future[JsonRpcResponse]] = {}
        self._request_counter = 0
        self._lock = asyncio.Lock()
        self._is_initialized = False
        self._server_info: dict[str, Any] = {}

    @property
    def is_connected(self) -> bool:
        """Return True if subprocess is alive and initialized."""
        return (
            self._process is not None and self._process.returncode is None and self._is_initialized
        )

    @property
    def server_name(self) -> str:
        """Return identifier name for this server."""
        return self.config.name

    async def __aenter__(self) -> McpClient:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()

    async def start(self) -> None:
        """Spawn MCP server process, start stdout reader, and execute initialization handshake."""
        async with self._lock:
            if self.is_connected:
                return

            env = os.environ.copy()
            env.update(self.config.env)

            logger.info(
                f"[McpClient:{self.config.name}] Spawning process: {self.config.command} {self.config.args}"
            )
            try:
                self._process = await asyncio.create_subprocess_exec(
                    self.config.command,
                    *self.config.args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
            except Exception as e:
                raise ToolExecutionError(
                    f"Failed to spawn MCP server '{self.config.name}': {e}"
                ) from e

            # Start background stdout reader
            self._reader_task = asyncio.create_task(self._stdout_reader_loop())

            # Perform MCP Handshake
            try:
                init_res = await asyncio.wait_for(
                    self._send_request(
                        "initialize",
                        {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "NexusAI", "version": "0.7.0"},
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
                self._is_initialized = True
                logger.info(f"[McpClient:{self.config.name}] Successfully initialized and ready")
            except Exception as e:
                await self.stop()
                raise ToolExecutionError(
                    f"MCP initialization failed for '{self.config.name}': {e}"
                ) from e

    async def stop(self) -> None:
        """Gracefully terminate MCP server subprocess and cancel pending requests."""
        async with self._lock:
            self._is_initialized = False

            # Cancel any pending futures
            for req_id, fut in list(self._pending_requests.items()):
                if not fut.done():
                    fut.cancel()
            self._pending_requests.clear()

            # Cancel reader task
            if self._reader_task and not self._reader_task.done():
                self._reader_task.cancel()
                try:
                    await self._reader_task
                except (asyncio.CancelledError, Exception):
                    pass
                self._reader_task = None

            # Terminate process cleanly
            if self._process:
                proc = self._process
                self._process = None
                if proc.returncode is None:
                    try:
                        proc.terminate()
                        try:
                            await asyncio.wait_for(proc.wait(), timeout=2.0)
                        except asyncio.TimeoutError:
                            proc.kill()
                            await proc.wait()
                    except ProcessLookupError:
                        pass
                    except Exception as e:
                        logger.warning(
                            f"[McpClient:{self.config.name}] Error stopping process: {e}"
                        )

            logger.info(f"[McpClient:{self.config.name}] Stopped")

    async def list_tools(self) -> list[McpToolDefinition]:
        """Fetch list of available tools declared by this MCP server."""
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
                    f"[McpClient:{self.config.name}] Skipping malformed tool definition: {item} ({e})"
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

    async def ping(self) -> bool:
        """Send ping request to check server responsiveness."""
        if not self.is_connected:
            return False
        try:
            res = await self._send_request("ping", {})
            return res.error is None
        except Exception:
            return False

    async def _send_request(self, method: str, params: dict[str, Any]) -> JsonRpcResponse:
        """Send a JSON-RPC 2.0 request and await response matched by request ID."""
        if not self._process or not self._process.stdin:
            raise ToolExecutionError(f"MCP process '{self.config.name}' stdin is closed")

        self._request_counter += 1
        req_id = self._request_counter

        request = JsonRpcRequest(id=req_id, method=method, params=params)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[JsonRpcResponse] = loop.create_future()
        self._pending_requests[req_id] = future

        msg_line = request.model_dump_json(exclude_none=True) + "\n"
        try:
            self._process.stdin.write(msg_line.encode("utf-8"))
            await self._process.stdin.drain()
        except Exception as e:
            self._pending_requests.pop(req_id, None)
            raise ToolExecutionError(f"Failed to write to '{self.config.name}' stdin: {e}") from e

        try:
            return await asyncio.wait_for(future, timeout=self.config.timeout_seconds)
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            raise ToolExecutionError(
                f"Timeout waiting for response from '{self.config.name}' for method '{method}'"
            )

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a fire-and-forget JSON-RPC 2.0 notification."""
        if not self._process or not self._process.stdin:
            return
        notification = JsonRpcRequest(id=None, method=method, params=params)
        msg_line = notification.model_dump_json(exclude_none=True) + "\n"
        try:
            self._process.stdin.write(msg_line.encode("utf-8"))
            await self._process.stdin.drain()
        except Exception as e:
            logger.warning(
                f"[McpClient:{self.config.name}] Failed to send notification '{method}': {e}"
            )

    async def _stdout_reader_loop(self) -> None:
        """Continuously read line-delimited JSON-RPC messages from server stdout."""
        if not self._process or not self._process.stdout:
            return

        reader = self._process.stdout
        while True:
            try:
                line = await reader.readline()
                if not line:
                    break  # EOF reached

                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue

                try:
                    payload = json.loads(line_str)
                except json.JSONDecodeError:
                    logger.debug(f"[McpClient:{self.config.name}] Non-JSON line: {line_str}")
                    continue

                # Match by response ID
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
            except Exception as e:
                logger.error(f"[McpClient:{self.config.name}] Reader error: {e}")
                break
