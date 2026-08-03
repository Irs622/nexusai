"""
Get Active Window Tool for macOS.
"""

from typing import Any
from pydantic import BaseModel

from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool
from nexusai.tools.system.applescript import execute_applescript


class EmptyInputSchema(BaseModel):
    """Empty schema for tools taking no input parameters."""

    pass


class GetActiveWindowTool(BaseTool):
    """Tool retrieving the name of the currently active application and window title."""

    name = "macos_get_active_window"
    description = "Retrieves the name of the currently active/frontmost application and its window title."
    risk_level = RiskLevel.LOW
    input_schema = EmptyInputSchema

    async def execute(self, **kwargs: Any) -> dict[str, str]:
        """Query System Events via AppleScript to get frontmost app and window title."""
        script = (
            'tell application "System Events"\n'
            '    set frontApp to name of first application process whose frontmost is true\n'
            '    tell process frontApp\n'
            '        try\n'
            '            set windowTitle to name of front window\n'
            '        on error\n'
            '            set windowTitle to ""\n'
            '        end try\n'
            '    end tell\n'
            'end tell\n'
            'return frontApp & "::" & windowTitle'
        )

        output = await execute_applescript(script)
        if "::" in output:
            app_name, window_title = output.split("::", 1)
        else:
            app_name, window_title = output, ""

        return {
            "active_app": app_name.strip(),
            "window_title": window_title.strip(),
        }
