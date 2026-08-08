"""
Generic AsyncTransaction context manager and UnitOfWork abstract interfaces for Kernel services.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import TypeVar

T = TypeVar("T")


class AsyncTransaction(ABC):
    """Abstract async transaction context manager interface."""

    @abstractmethod
    async def begin(self) -> None:
        """Begin transaction."""
        pass

    @abstractmethod
    async def commit(self) -> None:
        """Commit transaction."""
        pass

    @abstractmethod
    async def rollback(self) -> None:
        """Rollback transaction on failure."""
        pass

    async def __aenter__(self) -> AsyncTransaction:
        await self.begin()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        if exc_type is not None:
            await self.rollback()
            return False
        else:
            await self.commit()
            return True


class DefaultAsyncTransaction(AsyncTransaction):
    """Default no-op in-memory AsyncTransaction implementation."""

    async def begin(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class UnitOfWork(ABC):
    """Abstract Unit of Work pattern interface for OS services."""

    @abstractmethod
    def transaction(self) -> AsyncTransaction:
        """Return an AsyncTransaction context manager instance."""
        pass
