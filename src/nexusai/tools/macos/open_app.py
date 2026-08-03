"""
Open macOS Application Tool.
"""

from typing import Any
from pydantic import BaseModel, Field

from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool
from nexusai.tools.system.applescript import execute_applescript


class OpenAppInputSchema(BaseModel):
    """Input schema for macos_open_app tool."""

    app_name: str = Field(..., description="Name of the macOS application to activate (e.g. 'Google Chrome', 'Spotify', 'Terminal')")


class OpenAppTool(BaseTool):
    """Tool that opens or brings a macOS application to the frontmost active state."""

    name = "macos_open_app"
    description = "Opens or brings a macOS application to the foreground (e.g., 'Google Chrome', 'Spotify', 'Terminal')."
    risk_level = RiskLevel.LOW
    input_schema = OpenAppInputSchema

    async def execute(self, app_name: str, **kwargs: Any) -> str:
        """Activate specified application via AppleScript."""
        script = f'tell application "{app_name}" to activate'
        await execute_applescript(script)
        return f"Application '{app_name}' activated."
