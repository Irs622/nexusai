"""
RecoveryStrategy and PluginRecoveryEngine for failure handling and quarantine.
"""

from __future__ import annotations

from enum import Enum

from nexusai.plugins.contracts.state import PluginState
from nexusai.plugins.runtime.registry import PluginRegistry


class RecoveryStrategy(str, Enum):
    """Failure recovery strategy enumeration."""

    RETRY = "RETRY"
    BACKOFF = "BACKOFF"
    DISABLE = "DISABLE"
    QUARANTINE = "QUARANTINE"


class PluginRecoveryEngine:
    """Tracks consecutive plugin failures and executes automated quarantine policies."""

    def __init__(self, registry: PluginRegistry, max_failures: int = 3) -> None:
        self.registry = registry
        self.max_failures = max_failures
        self._failure_counts: dict[str, int] = {}
        self._quarantined: set[str] = set()

    def record_failure(self, plugin_id: str, error: str) -> RecoveryStrategy:
        """Record a runtime failure and evaluate appropriate recovery strategy."""
        count = self._failure_counts.get(plugin_id, 0) + 1
        self._failure_counts[plugin_id] = count

        if count >= self.max_failures:
            self._quarantined.add(plugin_id)
            self.registry.set_state(plugin_id, PluginState.FAILED)
            return RecoveryStrategy.QUARANTINE
        elif count == 1:
            return RecoveryStrategy.RETRY
        else:
            return RecoveryStrategy.BACKOFF

    def is_quarantined(self, plugin_id: str) -> bool:
        """Return True if plugin is currently quarantined."""
        return plugin_id in self._quarantined

    def clear_quarantine(self, plugin_id: str) -> None:
        """Clear quarantine status and failure count for plugin."""
        self._failure_counts.pop(plugin_id, None)
        self._quarantined.discard(plugin_id)
