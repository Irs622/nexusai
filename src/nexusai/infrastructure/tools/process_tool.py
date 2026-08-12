"""Governed ProcessTool adapter enforcing argv execution, bounded timeouts, output limits, and process reaping."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.observability import sanitize_attributes
from nexusai.brain.domain.tool_registry import ToolMetadata, ToolStatus, ToolTrustLevel
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult


class ProcessTool(IToolPort):
    """Real process execution adapter enforcing shell=False argv execution, bounded output, timeouts, and process reaping."""

    def __init__(
        self,
        working_dir: str | Path | None = None,
        default_timeout_seconds: float = 5.0,
        max_output_bytes: int = 1024 * 1024,  # 1 MB limit
    ) -> None:
        self.working_dir = Path(working_dir).resolve() if working_dir else None
        self.default_timeout_seconds = default_timeout_seconds
        self.max_output_bytes = max_output_bytes

    def _sanitize_env(self) -> dict[str, str]:
        """Sanitize process environment to prevent credential leakage into child processes."""
        sanitized = {}
        for k, v in os.environ.items():
            low_k = k.lower()
            if any(secret_kw in low_k for secret_kw in ("secret", "token", "password", "api_key", "auth", "private_key")):
                continue
            sanitized[k] = v
        return sanitized

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Execute subprocess using explicit argv vector with bounded timeout and output clipping."""
        cmd_args = request.parameters.get("argv", [])
        if not cmd_args:
            raw_cmd = request.parameters.get("command", "")
            if raw_cmd:
                cmd_args = raw_cmd.split()

        if not cmd_args:
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=False,
                error_message="Parameter 'argv' or 'command' vector is required",
            )

        timeout = float(request.parameters.get("timeout", self.default_timeout_seconds))
        env = self._sanitize_env()

        proc = None
        try:
            # P4-2-INV-05: Subprocess execution MUST use shell=False with argv vector!
            proc = await asyncio.create_subprocess_exec(
                cmd_args[0],
                *cmd_args[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir) if self.working_dir else None,
                env=env,
            )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                # Reaping invariant: Terminate and kill timed-out subprocess cleanly
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                return ToolExecutionResult(
                    request_id=request.execution_id,
                    tool_name=request.tool_name,
                    success=False,
                    error_message=f"Process execution timed out after {timeout} seconds",
                )

            stdout_str = stdout_data.decode("utf-8", errors="replace")[: self.max_output_bytes]
            stderr_str = stderr_data.decode("utf-8", errors="replace")[: self.max_output_bytes]

            if proc.returncode != 0:
                return ToolExecutionResult(
                    request_id=request.execution_id,
                    tool_name=request.tool_name,
                    success=False,
                    error_message=f"Process exited with non-zero code {proc.returncode}: {stderr_str or stdout_str}",
                )

            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=True,
                output=stdout_str or "Process completed with returncode 0",
            )

        except Exception as err:
            if proc and proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=False,
                error_message=f"Process execution error: {err}",
            )


def get_process_tool_metadata() -> ToolMetadata:
    """Return ToolMetadata for ProcessTool."""
    return ToolMetadata(
        tool_id="process_tool",
        name="Process Execution Tool",
        version="1.0.0",
        description="Governed argv subprocess execution",
        capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        status=ToolStatus.ENABLED,
        trust_level=ToolTrustLevel.VERIFIED,
    )
