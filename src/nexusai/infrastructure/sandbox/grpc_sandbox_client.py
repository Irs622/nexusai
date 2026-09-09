"""gRPC / TCP Sandbox Client implementing ISandboxExecutionPort interface."""

from __future__ import annotations

import asyncio
import json
import struct
from typing import Any

from loguru import logger

from nexusai.brain.domain.sandbox import SandboxResult, SandboxSpec
from nexusai.brain.ports.sandbox_execution_port import ISandboxExecutionPort
from nexusai.infrastructure.sandbox.grpc_sandbox_server import (
    GRPCSandboxServer,
    deserialize_sandbox_result,
    serialize_sandbox_spec,
)


class GRPCSandboxClient(ISandboxExecutionPort):
    """gRPC / TCP Client adapter implementing ISandboxExecutionPort protocol."""

    def __init__(
        self,
        target_address: str = "localhost:50051",
        server_double: GRPCSandboxServer | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.target_address = target_address
        self.timeout_seconds = timeout_seconds
        self.server_double = server_double
        self.server = server_double or GRPCSandboxServer()

    async def execute_in_sandbox(self, spec: SandboxSpec) -> SandboxResult:
        """Dispatch execution spec over gRPC/TCP to Sandbox Gateway server with fallback."""
        if self.server_double is not None or self.target_address == "in-process":
            return await self.server.handle_execution_request(spec)

        # Attempt network dispatch over TCP socket
        try:
            return await self._execute_over_network(spec)
        except (ConnectionRefusedError, OSError, asyncio.TimeoutError) as net_err:
            logger.debug(
                f"[GRPCSandboxClient] Network dispatch to {self.target_address} failed ({net_err}). "
                "Executing via local fallback gateway."
            )
            return await self.server.handle_execution_request(spec)

    async def _execute_over_network(self, spec: SandboxSpec) -> SandboxResult:
        """Send framed request over TCP to active Sandbox Gateway daemon."""
        if ":" in self.target_address:
            host, port_str = self.target_address.split(":", 1)
            port = int(port_str)
        else:
            host = self.target_address
            port = 50051

        # Determine network timeout
        effective_timeout = max(self.timeout_seconds, spec.limits.timeout_seconds + 5.0)

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=2.0,
        )

        try:
            spec_data: dict[str, Any] = serialize_sandbox_spec(spec)
            payload_bytes = json.dumps(spec_data).encode("utf-8")
            header = struct.pack("!I", len(payload_bytes))

            writer.write(header + payload_bytes)
            await writer.drain()

            res_length_bytes = await asyncio.wait_for(
                reader.readexactly(4),
                timeout=effective_timeout,
            )
            (res_len,) = struct.unpack("!I", res_length_bytes)

            res_payload_bytes = await asyncio.wait_for(
                reader.readexactly(res_len),
                timeout=effective_timeout,
            )
            res_dict = json.loads(res_payload_bytes.decode("utf-8"))
            return deserialize_sandbox_result(res_dict)

        finally:
            writer.close()
            await writer.wait_closed()
