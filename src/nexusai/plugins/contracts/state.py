"""
Plugin lifecycle states enum definition.
"""

from __future__ import annotations

from enum import Enum


class PluginState(str, Enum):
    """Granular 10-state plugin lifecycle enumeration."""

    DISCOVERED = "DISCOVERED"
    PARSED = "PARSED"
    VALIDATED = "VALIDATED"
    RESOLVED = "RESOLVED"
    LOADED = "LOADED"
    INITIALIZED = "INITIALIZED"
    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"
    UNLOADED = "UNLOADED"
    FAILED = "FAILED"

    def is_terminal(self) -> bool:
        """Return True if the state represents a terminal lifecycle state."""
        return self in (PluginState.UNLOADED, PluginState.FAILED)

    def is_active(self) -> bool:
        """Return True if the plugin is in an active running state."""
        return self == PluginState.ACTIVE
