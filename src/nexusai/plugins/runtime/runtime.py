"""
PluginRuntime managing active live plugin instances.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from nexusai.plugins.contracts.base import BasePlugin
from nexusai.plugins.contracts.state import PluginState


@dataclass
class LivePluginRecord:
    """Record holding active running plugin instance and background task references."""

    plugin_id: str
    instance: BasePlugin
    state: PluginState = PluginState.LOADED
    background_task: asyncio.Task[Any] | None = None


class PluginRuntime:
    """Manages active live instances and execution state of running plugins."""

    def __init__(self) -> None:
        self._records: dict[str, LivePluginRecord] = {}

    def attach_instance(self, plugin_id: str, instance: BasePlugin) -> None:
        """Attach live plugin instance."""
        self._records[plugin_id] = LivePluginRecord(plugin_id=plugin_id, instance=instance)

    def get_instance(self, plugin_id: str) -> BasePlugin | None:
        """Retrieve live instance by plugin ID."""
        record = self._records.get(plugin_id)
        return record.instance if record else None

    def detach_instance(self, plugin_id: str) -> LivePluginRecord | None:
        """Detach live instance from runtime."""
        return self._records.pop(plugin_id, None)

    def list_active_ids(self) -> list[str]:
        """Return list of active plugin IDs."""
        return list(self._records.keys())
