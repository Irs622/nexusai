"""
Native macOS Desktop Notification Tool.
"""

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool


async def send_macos_notification(title: str, message: str) -> None:
    """Send a native macOS desktop banner notification via osascript."""
    escaped_title = title.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    escaped_message = message.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

    script = f'display notification "{escaped_message}" with title "{escaped_title}"'
    try:
        process = await asyncio.create_subprocess_exec(
            "osascript",
            "-e",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
    except Exception:
        pass  # Do not fail application if notification permissions fail


class NotifyInputSchema(BaseModel):
    """Input schema for macos_send_notification tool."""

    title: str = Field(..., description="Title banner text for the macOS notification")
    message: str = Field(..., description="Body message text for the notification")


class NotifyTool(BaseTool):
    """Tool sending a native desktop banner notification on macOS."""

    name = "macos_send_notification"
    description = "Sends a native macOS desktop banner notification to the user."
    risk_level = RiskLevel.LOW
    input_schema = NotifyInputSchema

    async def execute(self, title: str, message: str, **kwargs: Any) -> str:
        """Deliver native macOS notification."""
        await send_macos_notification(title, message)
        return f"Desktop notification sent: '{title}' - {message}"
