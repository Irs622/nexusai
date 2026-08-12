"""gRPC Sandbox Gateway Server handling container dispatch and capability enforcement."""

from __future__ import annotations

import asyncio
from typing import Any

from nexusai.brain.domain.sandbox import SandboxResult, SandboxSpec
from nexusai.infrastructure.sandbox.container_runtime import ContainerRuntimeEngine


class GRPCSandboxServer:
    """gRPC Gateway server executing tools in isolated container runtimes."""

    def __init__(self) -> None:
        self.container_runtime = ContainerRuntimeEngine()

    async def handle_execution_request(self, spec: SandboxSpec) -> SandboxResult:
        """Handle incoming gRPC execution request and dispatch to container runtime."""
        return await self.container_runtime.run(spec)
