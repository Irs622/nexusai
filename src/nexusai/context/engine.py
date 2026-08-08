"""
Working Context Engine for passive environment and system awareness.
"""

from __future__ import annotations

import asyncio

import psutil
from pydantic import BaseModel

from nexusai.tools.macos.active_window import GetActiveWindowTool


class WorkingContext(BaseModel):
    """Snapshot model of the user's active desktop environment and hardware state."""

    active_application: str = "Unknown"
    active_window_title: str = "Unknown"
    git_branch: str | None = None
    cpu_usage_percent: float = 0.0
    memory_usage_percent: float = 0.0


class ContextEngine:
    """Engine gathering real-time working context from macOS and system hardware."""

    def __init__(self) -> None:
        self._active_window_tool = GetActiveWindowTool()

    async def _get_active_window(self) -> tuple[str, str]:
        """Fetch active application and window title safely."""
        try:
            res = await self._active_window_tool.execute()
            if isinstance(res, dict):
                return res.get("active_app", "Unknown"), res.get("window_title", "Unknown")
        except Exception:
            pass
        return "Unknown", "Unknown"

    async def _get_git_branch(self) -> str | None:
        """Fetch active Git branch name safely."""
        try:
            process = await asyncio.create_subprocess_shell(
                "git branch --show-current",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await process.communicate()
            if process.returncode == 0:
                branch = stdout_bytes.decode("utf-8", errors="replace").strip()
                return branch if branch else None
        except Exception:
            pass
        return None

    def _get_hardware_telemetry(self) -> tuple[float, float]:
        """Fetch CPU and Memory usage percentages safely."""
        try:
            cpu = float(psutil.cpu_percent(interval=None))
            mem = float(psutil.virtual_memory().percent)
            return cpu, mem
        except Exception:
            return 0.0, 0.0

    async def gather_context(self) -> WorkingContext:
        """Gather active desktop window, git branch, and system resource telemetry."""
        app_name, window_title = await self._get_active_window()
        branch = await self._get_git_branch()
        cpu, mem = self._get_hardware_telemetry()

        return WorkingContext(
            active_application=app_name,
            active_window_title=window_title,
            git_branch=branch,
            cpu_usage_percent=cpu,
            memory_usage_percent=mem,
        )
