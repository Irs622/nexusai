"""Controlled deterministic test tools for P4-1 End-to-End Runtime Integration testing."""

from __future__ import annotations

import asyncio
from typing import Any

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.tool_registry import ToolMetadata, ToolStatus, ToolTrustLevel
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult


class ControlledTestToolPort(IToolPort):
    """Deterministic IToolPort adapter tracking executions and tool call counts."""

    def __init__(self, failure_modes: dict[str, str] | None = None) -> None:
        self.call_count: int = 0
        self.executed_tools: list[str] = []
        self.failure_modes = failure_modes or {}
        self._lock = asyncio.Lock()

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        async with self._lock:
            self.call_count += 1
            self.executed_tools.append(request.tool_name)

        mode = self.failure_modes.get(request.tool_name, "success")
        if mode == "fail":
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=False,
                error_message=f"Controlled tool failure for {request.tool_name}",
            )
        elif mode == "timeout":
            await asyncio.sleep(0.01)
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=False,
                error_message=f"Timeout executing {request.tool_name}",
            )

        await asyncio.sleep(0.002)
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=request.tool_name,
            success=True,
            output=f"Controlled output for {request.tool_name}",
        )


def get_p4_1_test_tools() -> list[ToolMetadata]:
    """Return a list of registered ToolMetadata objects for P4-1 integration testing."""
    return [
        ToolMetadata(
            tool_id="echo_tool",
            name="Echo Tool",
            version="1.0.0",
            description="Echoes input",
            capabilities=frozenset({ToolCapability.FILE_READ}),
            status=ToolStatus.ENABLED,
            trust_level=ToolTrustLevel.BUILTIN,
        ),
        ToolMetadata(
            tool_id="file_read_tool",
            name="File Reader",
            version="1.0.0",
            description="Reads sandbox files",
            capabilities=frozenset({ToolCapability.FILE_READ}),
            status=ToolStatus.ENABLED,
            trust_level=ToolTrustLevel.BUILTIN,
        ),
        ToolMetadata(
            tool_id="file_write_tool",
            name="File Writer",
            version="1.0.0",
            description="Writes sandbox files",
            capabilities=frozenset({ToolCapability.FILE_WRITE}),
            status=ToolStatus.ENABLED,
            trust_level=ToolTrustLevel.BUILTIN,
        ),
        ToolMetadata(
            tool_id="process_exec_tool",
            name="Process Executor",
            version="1.0.0",
            description="Executes subcommands",
            capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
            status=ToolStatus.ENABLED,
            trust_level=ToolTrustLevel.VERIFIED,
        ),
        ToolMetadata(
            tool_id="revocable_tool",
            name="Revocable Tool",
            version="1.0.0",
            description="Tool subject to runtime revocation",
            capabilities=frozenset({ToolCapability.FILE_WRITE}),
            status=ToolStatus.ENABLED,
            trust_level=ToolTrustLevel.VERIFIED,
        ),
    ]
