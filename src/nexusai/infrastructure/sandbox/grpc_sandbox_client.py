"""gRPC Sandbox Client implementing ISandboxExecutionPort interface."""

from __future__ import annotations

import asyncio
from typing import Any

from nexusai.brain.domain.sandbox import SandboxResult, SandboxSpec
from nexusai.brain.ports.sandbox_execution_port import ISandboxExecutionPort
from nexusai.infrastructure.sandbox.grpc_sandbox_server import GRPCSandboxServer


class GRPCSandboxClient(ISandboxExecutionPort):
    """gRPC Client adapter implementing ISandboxExecutionPort protocol."""

    def __init__(self, target_address: str = "localhost:50051", server_double: GRPCSandboxServer | None = None) -> None:
        self.target_address = target_address
        self.server = server_double or GRPCSandboxServer()

    async def execute_in_sandbox(self, spec: SandboxSpec) -> SandboxResult:
        """Dispatch execution spec over gRPC to Sandbox Gateway server."""
        return await self.server.handle_execution_request(spec)
