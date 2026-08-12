"""
Terminal Shell Execution Tool with process group termination and subprocess tree cleanup.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from typing import Any

from pydantic import BaseModel, Field

from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool


class TerminalInputSchema(BaseModel):
    """Input schema for execute_terminal tool."""

    command: str = Field(..., description="The shell command string to execute in zsh terminal")
    timeout_seconds: float | None = Field(default=None, description="Optional timeout limit in seconds")


class TerminalTool(BaseTool):
    """Tool executing terminal commands on macOS via asyncio subprocess with process-group isolation and cleanup."""

    name = "execute_terminal"
    description = "Executes a shell command in the terminal on macOS and returns stdout, stderr, and exit code."
    risk_level = RiskLevel.HIGH
    input_schema = TerminalInputSchema

    async def _cleanup_process_group(self, process: asyncio.subprocess.Process) -> None:
        """Safely terminate and reap the subprocess and its process group without affecting parent processes."""
        if process.pid is None or process.returncode is not None:
            return

        pid = process.pid
        pgid: int | None = None

        if sys.platform != "win32":
            try:
                pgid = os.getpgid(pid)
                # Safety assertion: Never signal parent process group or current process
                if pgid == os.getpid() or pgid == os.getpgid(0):
                    pgid = None
            except (ProcessLookupError, OSError):
                pgid = None

        try:
            if pgid is not None and sys.platform != "win32":
                # Send SIGTERM to entire process group
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    pass

                try:
                    await asyncio.sleep(0.05)
                except asyncio.CancelledError:
                    pass

                if process.returncode is None:
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError, OSError):
                        pass
            else:
                # Fallback to direct process termination
                try:
                    process.terminate()
                except (ProcessLookupError, PermissionError, OSError):
                    pass

                try:
                    await asyncio.sleep(0.05)
                except asyncio.CancelledError:
                    pass

                if process.returncode is None:
                    try:
                        process.kill()
                    except (ProcessLookupError, PermissionError, OSError):
                        pass
        finally:
            try:
                await process.wait()
            except (ProcessLookupError, OSError):
                pass

    async def execute(self, command: str, **kwargs: Any) -> dict[str, Any]:
        """Execute command in shell with subprocess group isolation, timeout, and tree cleanup."""
        raw_timeout = kwargs.get("timeout_seconds") or kwargs.get("timeout")
        timeout_sec: float | None = float(raw_timeout) if raw_timeout is not None else 30.0

        extra_kwargs: dict[str, Any] = {}
        if sys.platform != "win32":
            extra_kwargs["start_new_session"] = True

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **extra_kwargs,
        )

        try:
            if timeout_sec and timeout_sec > 0:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=timeout_sec
                )
            else:
                stdout_bytes, stderr_bytes = await process.communicate()

            return {
                "command": command,
                "stdout": stdout_bytes.decode("utf-8", errors="replace"),
                "stderr": stderr_bytes.decode("utf-8", errors="replace"),
                "returncode": process.returncode or 0,
            }
        except (asyncio.TimeoutError, asyncio.CancelledError):
            await self._cleanup_process_group(process)
            raise
