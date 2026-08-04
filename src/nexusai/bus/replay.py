"""
EventReplayEngine for diagnostic playback and stream historical event replaying.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Sequence


class EventReplayEngine:
    """Manages historical event stream recording and replay capabilities."""

    def __init__(self, max_history: int = 1000) -> None:
        self.max_history = max_history
        self._history: list[tuple[float, Any]] = []

    def record_event(self, event: Any) -> None:
        """Record an event into historical event store."""
        timestamp = getattr(event, "timestamp", time.time())
        self._history.append((timestamp, event))
        if len(self._history) > self.max_history:
            self._history.pop(0)

    def get_history(
        self,
        since_timestamp: float | None = None,
        filter_fn: Callable[[Any], bool] | None = None,
    ) -> Sequence[Any]:
        """Return historical events filtered by timestamp or predicate."""
        events: list[Any] = []
        for ts, evt in self._history:
            if since_timestamp is not None and ts < since_timestamp:
                continue
            if filter_fn is not None and not filter_fn(evt):
                continue
            events.append(evt)
        return events

    def clear(self) -> None:
        """Clear recorded event history."""
        self._history.clear()
