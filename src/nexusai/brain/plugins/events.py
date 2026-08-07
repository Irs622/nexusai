"""
Priority-based ExtensionEvent plugin system, PluginFailurePolicy, and PriorityExtensionDispatcher.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from nexusai.brain.runtime.context import ExecutionContext
from nexusai.logging.logger import logger


class PluginFailurePolicy(str, Enum):
    """Failure policy indicating how dispatcher handles plugin execution errors."""

    CONTINUE_ON_ERROR = "continue_on_error"  # Log error and continue executing remaining plugins/turn
    STOP_ON_ERROR = "stop_on_error"  # Halt execution and re-raise plugin exception


@dataclass
class ExtensionEvent:
    """Plugin extension event container with priority metadata.

    Attributes:
        event_name: Unique event discriminator name.
        context: ExecutionContext transport reference.
        priority: Priority integer (lower integer = higher execution precedence, e.g. Audit=1, Safety=10).
        failure_policy: Policy indicating how plugin errors are handled.
        payload: Event payload parameters.
    """

    event_name: str
    context: ExecutionContext
    priority: int = 100
    failure_policy: PluginFailurePolicy = PluginFailurePolicy.CONTINUE_ON_ERROR
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HandlerRegistration:
    """Internal registration entry for event handlers."""

    event_name: str
    handler: Callable[[ExtensionEvent], Awaitable[None]]
    priority: int = 100
    failure_policy: PluginFailurePolicy = PluginFailurePolicy.CONTINUE_ON_ERROR


class PriorityExtensionDispatcher:
    """Deterministic priority-ordered plugin extension event dispatcher."""

    def __init__(self) -> None:
        self._handlers: list[HandlerRegistration] = []

    def register_handler(
        self,
        event_name: str,
        handler: Callable[[ExtensionEvent], Awaitable[None]],
        priority: int = 100,
        failure_policy: PluginFailurePolicy = PluginFailurePolicy.CONTINUE_ON_ERROR,
    ) -> None:
        """Register a handler for a specific event name with integer priority and failure policy.

        Args:
            event_name: Target event name.
            handler: Async callback accepting ExtensionEvent.
            priority: Priority integer (lower integer = higher precedence).
            failure_policy: Policy for error handling.
        """
        registration = HandlerRegistration(
            event_name=event_name,
            handler=handler,
            priority=priority,
            failure_policy=failure_policy,
        )
        self._handlers.append(registration)
        logger.debug(f"Registered plugin handler for '{event_name}' (priority={priority}, policy={failure_policy.value})")

    async def dispatch(self, event: ExtensionEvent) -> None:
        """Dispatch event to registered handlers sorted by priority integer ascending.

        Args:
            event: The ExtensionEvent to dispatch.
        """
        matching_handlers = [h for h in self._handlers if h.event_name == event.event_name]
        matching_handlers.sort(key=lambda h: h.priority)

        for registration in matching_handlers:
            try:
                event.priority = registration.priority
                event.failure_policy = registration.failure_policy
                await registration.handler(event)
            except Exception as e:
                logger.error(
                    f"Plugin handler error for '{event.event_name}' (priority={registration.priority}): {e}"
                )
                if registration.failure_policy == PluginFailurePolicy.STOP_ON_ERROR:
                    raise
