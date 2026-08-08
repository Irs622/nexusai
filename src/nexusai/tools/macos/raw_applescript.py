"""
Raw AppleScript Execution Tool.
"""

from typing import Any

from pydantic import BaseModel, Field

from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool
from nexusai.tools.system.applescript import execute_applescript


class RawAppleScriptInputSchema(BaseModel):
    """Input schema for macos_execute_applescript tool."""

    script: str = Field(..., description="Raw AppleScript code string to execute")


class RawAppleScriptTool(BaseTool):
    """Tool executing raw AppleScript for low-level UI and application automation."""

    name = "macos_execute_applescript"
    description = "Executes raw AppleScript code for advanced UI automation. Extremely powerful."
    risk_level = RiskLevel.CRITICAL
    input_schema = RawAppleScriptInputSchema

    async def execute(self, script: str, **kwargs: Any) -> str:
        """Execute raw AppleScript code."""
        return await execute_applescript(script)
