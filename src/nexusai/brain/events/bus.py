"""AgentEventBus for decoupled domain event publishing and subscription."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Type, Union


@dataclass(frozen=True)
class AgentEvent:
    """Base class for all domain events."""

    event_id: str
    session_id: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class PlannerFinishedEvent(AgentEvent):
    """Event emitted when planner completes plan generation."""

    goal_description: str = ""
    step_count: int = 0


@dataclass(frozen=True)
class ExecutionStartedEvent(AgentEvent):
    """Event emitted when PlanGraph execution starts."""

    node_count: int = 0


@dataclass(frozen=True)
class ExecutionFinishedEvent(AgentEvent):
    """Event emitted when PlanGraph execution completes."""

    success: bool = True
    executed_steps: int = 0


@dataclass(frozen=True)
class ToolFailedEvent(AgentEvent):
    """Event emitted when a tool execution fails."""

    tool_name: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class MemoryUpdatedEvent(AgentEvent):
    """Event emitted when MemoryIndexer is updated."""

    item_id: str = ""
    memory_type: str = ""


@dataclass(frozen=True)
class DecisionRecordedEvent(AgentEvent):
    """Event emitted when a DecisionTrace is recorded into DecisionDataset."""

    trace_id: str = ""
    chosen_action: str = ""


EventHandler = Callable[[AgentEvent], Union[Any, Coroutine[Any, Any, Any]]]


class AgentEventBus:
    """Publish-Subscribe event bus for decoupled Agent Runtime domain events."""

    def __init__(self) -> None:
        self._handlers: dict[Type[AgentEvent], list[EventHandler]] = {}

    def subscribe(self, event_type: Type[AgentEvent], handler: EventHandler) -> None:
        """Subscribe a handler callback to a specific event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def publish(self, event: AgentEvent) -> None:
        """Publish an event to all registered subscribers."""
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])

        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
