"""
macOS Screen Capture Tool using screencapture utility.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from nexusai.core.errors import ToolExecutionError
from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool


class EmptyInputSchema(BaseModel):
    """Empty schema for tools taking no input parameters."""

    pass


class ScreenCaptureTool(BaseTool):
    """Tool capturing a silent screenshot of the macOS screen."""

    name = "vision_capture_screen"
    description = (
        "Takes a screenshot of the user's current macOS screen. "
        "Use this when the user asks you to 'look' at something, read an error on screen, or analyze a visual element."
    )
    risk_level = RiskLevel.LOW
    input_schema = EmptyInputSchema

    async def execute(self, **kwargs: Any) -> dict[str, str]:
        """Capture screenshot to temporary file."""
        temp_dir = Path(tempfile.gettempdir())
        target_path = temp_dir / "nexusai_screenshot.png"

        try:
            process = await asyncio.create_subprocess_exec(
                "screencapture",
                "-x",
                "-t",
                "png",
                str(target_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr_bytes = await process.communicate()

            if process.returncode != 0:
                stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
                raise ToolExecutionError(
                    f"Screen capture failed with exit code {process.returncode}: {stderr_str}",
                    details={"returncode": str(process.returncode), "stderr": stderr_str},
                )

            return {
                "type": "image_path",
                "path": str(target_path),
            }
        except Exception as e:
            if isinstance(e, ToolExecutionError):
                raise
            raise ToolExecutionError(f"Failed to execute screencapture: {e}") from e
