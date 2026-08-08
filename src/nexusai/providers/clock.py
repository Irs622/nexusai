"""Runtime Clock abstraction for deterministic time testing and timeout simulation."""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from nexusai.core.annotations import stable


@stable
class Clock(ABC):
    """Abstract interface for system time operations."""

    @abstractmethod
    def now(self) -> datetime:
        """Return the current UTC datetime."""
        ...

    @abstractmethod
    def time(self) -> float:
        """Return the current UNIX timestamp in seconds."""
        ...

    @abstractmethod
    async def sleep(self, seconds: float) -> None:
        """Asynchronously sleep for a duration in seconds."""
        ...


@stable
class SystemClock(Clock):
    """Standard system clock implementation."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def time(self) -> float:
        return time.time()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


@stable
class TestClock(Clock):
    """Controllable test clock for deterministic time travel testing."""

    def __init__(self, initial_time: float = 1700000000.0) -> None:
        self._current_time = initial_time

    def now(self) -> datetime:
        return datetime.fromtimestamp(self._current_time, tz=timezone.utc)

    def time(self) -> float:
        return self._current_time

    def advance(self, seconds: float) -> None:
        """Advance test clock by seconds."""
        self._current_time += seconds

    async def sleep(self, seconds: float) -> None:
        """Advance test clock without real sleep delay."""
        self.advance(seconds)
