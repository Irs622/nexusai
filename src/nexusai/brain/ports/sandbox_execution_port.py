"""Protocol port interface for gRPC container sandbox execution."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from nexusai.brain.domain.sandbox import SandboxResult, SandboxSpec


@runtime_checkable
class ISandboxExecutionPort(Protocol):
    """Protocol port interface for sandbox container execution gateway."""

    async def execute_in_sandbox(self, spec: SandboxSpec) -> SandboxResult:
        """Execute a tool request in an isolated gRPC container sandbox."""
        ...
