"""IToolPort interface contract and execution containers for Brain Runtime tool isolation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4


@dataclass(frozen=True, init=False)
class ToolExecutionRequest:
    """Standardized tool execution request container."""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    execution_id: UUID | str = field(default_factory=uuid4)
    timeout_seconds: float = 30.0

    def __init__(
        self,
        *args: Any,
        tool_name: str | None = None,
        arguments: dict[str, Any] | None = None,
        execution_id: UUID | str | None = None,
        timeout_seconds: float = 30.0,
        **kwargs: Any,
    ) -> None:
        actual_tool_name = tool_name
        actual_arguments = arguments
        actual_execution_id = execution_id
        actual_timeout = timeout_seconds

        if args:
            if len(args) == 1:
                actual_tool_name = args[0]
            elif len(args) == 2:
                if isinstance(args[1], str):
                    actual_execution_id = args[0]
                    actual_tool_name = args[1]
                else:
                    actual_tool_name = args[0]
                    actual_arguments = args[1]
            elif len(args) >= 3:
                if isinstance(args[1], str):
                    actual_execution_id = args[0]
                    actual_tool_name = args[1]
                    actual_arguments = args[2]
                else:
                    actual_tool_name = args[0]
                    actual_arguments = args[1]
                    actual_execution_id = args[2]
                if len(args) >= 4:
                    actual_timeout = args[3]

        if actual_tool_name is None:
            actual_tool_name = ""
        if actual_arguments is None:
            actual_arguments = {}
        elif not isinstance(actual_arguments, dict):
            try:
                actual_arguments = dict(actual_arguments)
            except Exception:
                actual_arguments = {}
        if actual_execution_id is None:
            actual_execution_id = uuid4()

        object.__setattr__(self, "tool_name", actual_tool_name)
        object.__setattr__(self, "arguments", actual_arguments)
        object.__setattr__(self, "execution_id", actual_execution_id)
        object.__setattr__(self, "timeout_seconds", float(actual_timeout))

    @property
    def parameters(self) -> dict[str, Any]:
        """Alias for arguments payload dictionary."""
        return self.arguments


@dataclass(frozen=True, init=False)
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

    def __init__(
        self,
        *args: Any,
        tool_name: str | None = None,
        success: bool | None = None,
        output: Any = None,
        error_message: str | None = None,
        execution_time_ms: float = 0.0,
        request_id: UUID | str | None = None,
        result_data: Any = None,
        result: Any = None,
        **kwargs: Any,
    ) -> None:
        actual_tool_name = tool_name
        actual_success = success
        actual_output = output
        actual_error_message = error_message
        actual_execution_time_ms = execution_time_ms
        actual_request_id = request_id
        actual_result_data = result_data if result_data is not None else result
        actual_result = result if result is not None else result_data

        if args:
            if (
                len(args) >= 2
                and isinstance(args[1], str)
                and (len(args) >= 3 or success is not None or "success" in kwargs)
            ):
                actual_request_id = args[0]
                actual_tool_name = args[1]
                if len(args) >= 3 and actual_success is None:
                    actual_success = args[2]
                if len(args) >= 4 and actual_output is None:
                    actual_output = args[3]
                if len(args) >= 5 and actual_error_message is None:
                    actual_error_message = args[4]
            elif len(args) == 1:
                actual_tool_name = args[0]
            else:
                actual_tool_name = args[0]
                if actual_success is None and len(args) >= 2:
                    actual_success = args[1]
                if len(args) >= 3 and actual_output is None:
                    actual_output = args[2]
                if len(args) >= 4 and actual_error_message is None:
                    actual_error_message = args[3]

        if actual_tool_name is None:
            actual_tool_name = ""
        if actual_success is None:
            actual_success = True

        if actual_output is None and actual_result_data is not None:
            actual_output = actual_result_data
        if actual_result_data is None and actual_output is not None:
            actual_result_data = actual_output
        if actual_result is None and actual_output is not None:
            actual_result = actual_output

        object.__setattr__(self, "tool_name", actual_tool_name)
        object.__setattr__(self, "success", bool(actual_success))
        object.__setattr__(self, "output", actual_output)
        object.__setattr__(self, "error_message", actual_error_message)
        object.__setattr__(self, "execution_time_ms", float(actual_execution_time_ms))
        object.__setattr__(self, "request_id", actual_request_id)
        object.__setattr__(self, "result_data", actual_result_data)
        object.__setattr__(self, "result", actual_result)


@runtime_checkable
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
