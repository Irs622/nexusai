"""
CQRS Message Bus: CommandBus, QueryBus, and EventBus.
"""

from __future__ import annotations

import asyncio
from typing import TypeVar, Callable, Awaitable, Any

from nexusai.core.errors import CommandExecutionError, QueryExecutionError
from nexusai.logging.logger import log_audit

TCommand = TypeVar("TCommand")
TQuery = TypeVar("TQuery")
TEvent = TypeVar("TEvent")
TResult = TypeVar("TResult")


class CommandBus:
    """Dispatches imperative commands to registered command handlers."""

    def __init__(self) -> None:
        self._handlers: dict[type[Any], Callable[[Any], Awaitable[Any]]] = {}

    def register(
        self,
        command_type: type[TCommand],
        handler: Callable[[TCommand], Awaitable[Any]],
    ) -> None:
        """Register a command handler."""
        if command_type in self._handlers:
            raise CommandExecutionError(f"Handler already registered for command {command_type.__name__}")
        self._handlers[command_type] = handler

    async def dispatch(self, command: Any) -> Any:
        """Dispatch command to its registered handler."""
        command_type = type(command)
        if command_type not in self._handlers:
            raise CommandExecutionError(f"No handler registered for command {command_type.__name__}")

        try:
            return await self._handlers[command_type](command)
        except CommandExecutionError:
            raise
        except Exception as e:
            raise CommandExecutionError(f"Execution failed for command {command_type.__name__}: {e}") from e


class QueryBus:
    """Dispatches read queries to registered query handlers."""

    def __init__(self) -> None:
        self._handlers: dict[type[Any], Callable[[Any], Awaitable[Any]]] = {}

    def register(
        self,
        query_type: type[TQuery],
        handler: Callable[[TQuery], Awaitable[TResult]],
    ) -> None:
        """Register a query handler."""
        if query_type in self._handlers:
            raise QueryExecutionError(f"Handler already registered for query {query_type.__name__}")
        self._handlers[query_type] = handler

    async def execute(self, query: Any) -> Any:
        """Execute query via its registered handler."""
        query_type = type(query)
        if query_type not in self._handlers:
            raise QueryExecutionError(f"No handler registered for query {query_type.__name__}")

        try:
            return await self._handlers[query_type](query)
        except QueryExecutionError:
            raise
        except Exception as e:
            raise QueryExecutionError(f"Execution failed for query {query_type.__name__}: {e}") from e


class EventBus:
    """Asynchronous Pub/Sub Event Bus for domain events."""

    def __init__(self) -> None:
        self._subscribers: dict[type[Any], list[Callable[[Any], Awaitable[None]]]] = {}

    def subscribe(
        self,
        event_type: type[TEvent],
        subscriber: Callable[[TEvent], Awaitable[None]],
    ) -> None:
        """Subscribe to a domain event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(subscriber)

    async def publish(self, event: Any) -> None:
        """Publish domain event asynchronously to all subscribers."""
        event_type = type(event)
        subscribers = self._subscribers.get(event_type, [])

        if subscribers:
            tasks = [subscriber(event) for subscriber in subscribers]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    log_audit(
                        "EVENT_SUBSCRIBER_ERROR",
                        {
                            "event": event_type.__name__,
                            "error": str(res),
                        },
                    )

