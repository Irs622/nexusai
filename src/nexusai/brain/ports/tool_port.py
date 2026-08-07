"""IToolPort interface contract and execution containers for Brain Runtime tool isolation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID, uuid4


@dataclass(frozen=True)
class ToolExecutionRequest:
    """Standardized tool execution request container.

    Attributes:
        tool_name: Registered tool identifier name.
        arguments: Tool parameter dictionary.
        execution_id: Unique UUID tracking execution attempt.
        timeout_seconds: Maximum execution time ceiling.
    """

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    execution_id: UUID = field(default_factory=uuid4)
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class ToolExecutionResult:
    """Standardized tool execution result container returned by IToolPort implementations.

    Attributes:
        tool_name: Executed tool identifier name.
        success: Boolean success signal.
        output: Raw output payload from tool.
        error_message: Optional error message string if execution failed.
        execution_time_ms: Measured tool execution duration in milliseconds.
    """

    tool_name: str
    success: bool
    output: Any = None
    error_message: str | None = None
    execution_time_ms: float = 0.0


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
