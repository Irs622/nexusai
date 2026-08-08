"""
Git Repository Context Tools.
"""

import asyncio
from typing import Any

from pydantic import BaseModel

from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool


class EmptyInputSchema(BaseModel):
    """Empty schema for tools taking no input parameters."""

    pass


class GitStatusTool(BaseTool):
    """Tool retrieving the current Git repository status."""

    name = "workspace_git_status"
    description = "Checks and returns current Git branch and working tree status."
    risk_level = RiskLevel.LOW
    input_schema = EmptyInputSchema

    async def execute(self, **kwargs: Any) -> str:
        """Execute git status via shell subprocess."""
        try:
            process = await asyncio.create_subprocess_shell(
                "git status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await process.communicate()
            stdout_str = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()

            if process.returncode != 0:
                return f"Git error (exit code {process.returncode}): {stderr_str or stdout_str}"

            return stdout_str or "Git status clean."
        except Exception as e:
            return f"Error executing git status: {e}"
