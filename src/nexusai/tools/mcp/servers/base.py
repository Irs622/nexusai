"""Base standard I/O (stdio) JSON-RPC 2.0 server framework for Model Context Protocol (MCP)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
import json
import sys
from typing import Any

from nexusai.tools.mcp.models import (
    McpCallToolResult,
    McpToolContent,
    McpToolDefinition,
)

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any] | Any]


class McpServerBase:
    """Base class for stdio-based MCP servers conforming to Model Context Protocol (2024-11-05)."""

    def __init__(self, name: str, version: str = "1.0.0", description: str = "") -> None:
        self.name = name
        self.version = version
        self.description = description
        self._tools: dict[str, McpToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._is_initialized = False

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: ToolHandler,
    ) -> None:
        """Register a tool definition and its execution handler.

        Args:
            name: Unique name of the tool.
            description: Plain text description of what the tool does.
            input_schema: JSON Schema dictionary describing expected parameters.
            handler: Callable accepting kwargs dict and returning result.
        """
        definition = McpToolDefinition(
            name=name,
            description=description,
            inputSchema=input_schema,
        )
        self._tools[name] = definition
        self._handlers[name] = handler

    def log(self, message: str) -> None:
        """Log message to standard error to prevent corrupting standard output JSON-RPC stream."""
        sys.stderr.write(f"[{self.name}] {message}\n")
        sys.stderr.flush()

    async def handle_request(self, request_data: dict[str, Any]) -> dict[str, Any] | None:
        """Process a single JSON-RPC 2.0 request or notification and return response dict if required."""
        jsonrpc = request_data.get("jsonrpc", "2.0")
        req_id = request_data.get("id")
        method = request_data.get("method")
        params = request_data.get("params") or {}

        # If it's a notification without id and not requiring response
        is_notification = req_id is None

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": self.name,
                        "version": self.version,
                    },
                }
                return {"jsonrpc": jsonrpc, "id": req_id, "result": result}

            elif method == "notifications/initialized":
                self._is_initialized = True
                self.log("Client completed initialization handshake")
                return None

            elif method == "ping":
                return {"jsonrpc": jsonrpc, "id": req_id, "result": {}}

            elif method == "tools/list":
                tools_list = [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.input_schema,
                    }
                    for tool in self._tools.values()
                ]
                return {"jsonrpc": jsonrpc, "id": req_id, "result": {"tools": tools_list}}

            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments") or {}

                if not tool_name or tool_name not in self._handlers:
                    error_payload = {
                        "jsonrpc": jsonrpc,
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Tool '{tool_name}' not found",
                        },
                    }
                    return error_payload

                handler = self._handlers[tool_name]
                try:
                    res = handler(tool_args)
                    if asyncio.iscoroutine(res):
                        call_res = await res
                    else:
                        call_res = res

                    # Normalize output into McpCallToolResult
                    if isinstance(call_res, McpCallToolResult):
                        result_dict = call_res.model_dump(by_alias=True)
                    elif isinstance(call_res, dict):
                        result_dict = McpCallToolResult(
                            content=[
                                McpToolContent(type="text", text=json.dumps(call_res, indent=2))
                            ],
                            isError=False,
                        ).model_dump(by_alias=True)
                    else:
                        result_dict = McpCallToolResult(
                            content=[McpToolContent(type="text", text=str(call_res))],
                            isError=False,
                        ).model_dump(by_alias=True)

                    return {"jsonrpc": jsonrpc, "id": req_id, "result": result_dict}

                except Exception as exc:
                    self.log(f"Execution error in tool '{tool_name}': {exc}")
                    err_result = McpCallToolResult(
                        content=[McpToolContent(type="text", text=f"Error: {exc}")],
                        isError=True,
                    ).model_dump(by_alias=True)
                    return {"jsonrpc": jsonrpc, "id": req_id, "result": err_result}

            else:
                if is_notification:
                    return None
                return {
                    "jsonrpc": jsonrpc,
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method '{method}' not found",
                    },
                }

        except Exception as exc:
            self.log(f"Unhandled server error: {exc}")
            if is_notification:
                return None
            return {
                "jsonrpc": jsonrpc,
                "id": req_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal server error: {exc}",
                },
            }

    async def _read_stdin_lines(self) -> AsyncIterator[str]:
        """Asynchronously stream lines from standard input."""
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        try:
            await loop.connect_read_pipe(lambda: protocol, sys.stdin)
            while True:
                line_bytes = await reader.readline()
                if not line_bytes:
                    break
                yield line_bytes.decode("utf-8")
        except Exception:
            # Fallback to threaded readline
            while True:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                yield line

    async def run_stdio(self) -> None:
        """Run the stdio message loop until EOF on standard input."""
        self.log("Server listening on stdio...")
        async for raw_line in self._read_stdin_lines():
            line = raw_line.strip()
            if not line:
                continue

            try:
                request_obj = json.loads(line)
            except json.JSONDecodeError as err:
                self.log(f"Invalid JSON received: {err}")
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()
                continue

            response = await self.handle_request(request_obj)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

        self.log("Server stdio closed; shutting down")
