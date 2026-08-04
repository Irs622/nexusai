"""
TaskSupervisor for tracking and cancelling plugin background tasks.
"""

from __future__ import annotations

import asyncio
from typing import Any


class TaskSupervisor:
    """Manages async background tasks spawned by plugins for clean shutdown."""

    def __init__(self) -> None:
        self._tasks: dict[str, list[asyncio.Task[Any]]] = {}

    def track_task(self, plugin_id: str, task: asyncio.Task[Any]) -> None:
        """Register a background asyncio task to be supervised."""
        if plugin_id not in self._tasks:
            self._tasks[plugin_id] = []
        self._tasks[plugin_id].append(task)

        # Cleanup on task completion
        def _on_done(t: asyncio.Task[Any]) -> None:
            if plugin_id in self._tasks and t in self._tasks[plugin_id]:
                self._tasks[plugin_id].remove(t)

        task.add_done_callback(_on_done)

    def get_tasks(self, plugin_id: str) -> list[asyncio.Task[Any]]:
        """Return active tasks tracked for given plugin ID."""
        return list(self._tasks.get(plugin_id, []))

    async def cancel_plugin_tasks(self, plugin_id: str, timeout: float = 2.0) -> None:
        """Cancel and await all tracked background tasks for given plugin ID."""
        tasks = self._tasks.pop(plugin_id, [])
        if not tasks:
            return

        for task in tasks:
            if not task.done():
                task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
