"""IToolPort interface contract and execution containers for Brain Runtime tool isolation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID, uuid4


@dataclass(frozen=True)
class ToolExecutionRequest:
    """Standardized tool execution request container."""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    execution_id: UUID | str = field(default_factory=uuid4)
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class ToolExecutionResult:
    """Standardized tool execution result container returned by IToolPort implementations."""

    tool_name: str
    success: bool
    output: Any = None
    error_message: str | None = None
    execution_time_ms: float = 0.0
    request_id: UUID | str | None = None
    result_data: Any = None
    result: Any = None


class IToolPort(Protocol):
    """Abstract Tool Port interface decoupling Brain Runtime from tool registry implementations."""

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Execute a tool request within sandboxed execution environment.

        Args:
            request: ToolExecutionRequest parameters.

        Returns:
            ToolExecutionResult entity.
        """
        ...
