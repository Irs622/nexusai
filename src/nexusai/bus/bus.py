"""
CQRS Message Bus: CommandBus, QueryBus, and EventBus with Filter, Replay, and Telemetry support.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from nexusai.bus.replay import EventReplayEngine
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
            raise CommandExecutionError(
                f"Handler already registered for command {command_type.__name__}"
            )
        self._handlers[command_type] = handler

    async def dispatch(self, command: Any) -> Any:
        """Dispatch command to its registered handler."""
        command_type = type(command)
        if command_type not in self._handlers:
            raise CommandExecutionError(
                f"No handler registered for command {command_type.__name__}"
            )

        try:
            return await self._handlers[command_type](command)
        except CommandExecutionError:
            raise
        except Exception as e:
            raise CommandExecutionError(
                f"Execution failed for command {command_type.__name__}: {e}"
            ) from e


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
            raise QueryExecutionError(
                f"Execution failed for query {query_type.__name__}: {e}"
            ) from e


@dataclass
class EventSubscription:
    """Record holding subscriber callback and optional predicate filter."""

    subscriber: Callable[[Any], Awaitable[None]]
    filter_fn: Callable[[Any], bool] | None = None


class EventBus:
    """Asynchronous Pub/Sub Event Bus for domain events with filtering, replay, and telemetry."""

    def __init__(self, enable_replay: bool = True) -> None:
        self._subscribers: dict[type[Any], list[EventSubscription]] = {}
        self._interceptors: list[Callable[[Any], Awaitable[None]]] = []
        self._replay_engine: EventReplayEngine | None = (
            EventReplayEngine() if enable_replay else None
        )

    def subscribe(
        self,
        event_type: type[TEvent],
        subscriber: Callable[[TEvent], Awaitable[None]],
        filter_fn: Callable[[TEvent], bool] | None = None,
    ) -> None:
        """Subscribe to a domain event type with an optional predicate filter."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        subscription = EventSubscription(
            subscriber=subscriber,
            filter_fn=filter_fn,
        )
        self._subscribers[event_type].append(subscription)

    def add_interceptor(self, interceptor: Callable[[Any], Awaitable[None]]) -> None:
        """Add a global event interceptor middleware."""
        self._interceptors.append(interceptor)

    @property
    def replay_engine(self) -> EventReplayEngine | None:
        """Return event replay engine."""
        return self._replay_engine

    async def publish(self, event: Any) -> None:
        """Publish domain event asynchronously to all matching subscribers."""
        if self._replay_engine:
            self._replay_engine.record_event(event)

        # Run interceptors
        for interceptor in self._interceptors:
            try:
                await interceptor(event)
            except Exception as e:
                log_audit(
                    "EVENT_INTERCEPTOR_ERROR", {"event": type(event).__name__, "error": str(e)}
                )

        event_type = type(event)
        subscriptions = self._subscribers.get(event_type, [])

        if subscriptions:
            tasks: list[Awaitable[None]] = []
            for sub in subscriptions:
                if sub.filter_fn is None or sub.filter_fn(event):
                    tasks.append(sub.subscriber(event))

            if tasks:
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

    async def replay(
        self,
        since_timestamp: float | None = None,
        filter_fn: Callable[[Any], bool] | None = None,
    ) -> None:
        """Replay historical events matching criteria."""
        if not self._replay_engine:
            return
        history = self._replay_engine.get_history(
            since_timestamp=since_timestamp, filter_fn=filter_fn
        )
        for event in history:
            await self.publish(event)
