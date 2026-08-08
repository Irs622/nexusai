"""
Terminal Shell Execution Tool.
"""

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool


class TerminalInputSchema(BaseModel):
    """Input schema for execute_terminal tool."""

    command: str = Field(..., description="The shell command string to execute in zsh terminal")


class TerminalTool(BaseTool):
    """Tool executing terminal commands on macOS via asyncio subprocess."""

    name = "execute_terminal"
    description = "Executes a shell command in the terminal on macOS and returns stdout, stderr, and exit code."
    risk_level = RiskLevel.HIGH
    input_schema = TerminalInputSchema

    async def execute(self, command: str, **kwargs: Any) -> dict[str, Any]:
        """Execute command in shell and capture outputs."""
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_bytes, stderr_bytes = await process.communicate()

        return {
            "command": command,
            "stdout": stdout_bytes.decode("utf-8", errors="replace"),
            "stderr": stderr_bytes.decode("utf-8", errors="replace"),
            "returncode": process.returncode or 0,
        }
