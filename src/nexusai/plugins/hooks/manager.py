"""
HookRegistry and HookManager middleware runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexusai.plugins.hooks.hooks import HookHandler, HookPayload, HookType
from nexusai.logging.logger import logger


@dataclass(frozen=True)
class RegisteredHook:
    """Registered hook record holding handler function and execution priority."""

    plugin_id: str
    hook_type: HookType
    handler: HookHandler
    priority: int = 100  # Lower numbers execute earlier


class HookRegistry:
    """Centralized registry for plugin interceptor hooks."""

    def __init__(self) -> None:
        self._hooks: dict[HookType, list[RegisteredHook]] = {}

    def register_hook(
        self,
        plugin_id: str,
        hook_type: HookType,
        handler: HookHandler,
        priority: int = 100,
    ) -> None:
        """Register a hook interceptor handler."""
        if hook_type not in self._hooks:
            self._hooks[hook_type] = []

        record = RegisteredHook(
            plugin_id=plugin_id,
            hook_type=hook_type,
            handler=handler,
            priority=priority,
        )
        self._hooks[hook_type].append(record)
        # Sort by priority (ascending order)
        self._hooks[hook_type].sort(key=lambda h: h.priority)

    def unregister_plugin_hooks(self, plugin_id: str) -> None:
        """Unregister all hook handlers registered by a specific plugin."""
        for hook_type in list(self._hooks.keys()):
            self._hooks[hook_type] = [h for h in self._hooks[hook_type] if h.plugin_id != plugin_id]

    def get_hooks(self, hook_type: HookType) -> list[RegisteredHook]:
        """Return list of registered hooks for a given hook type in priority order."""
        return list(self._hooks.get(hook_type, []))


class HookManager:
    """Executes registered hook handlers sequentially across the middleware pipeline."""

    def __init__(self, registry: HookRegistry | None = None) -> None:
        self.registry = registry or HookRegistry()

    async def trigger_hook(
        self,
        hook_type: HookType,
        plugin_id: str,
        initial_data: dict[str, Any] | None = None,
    ) -> HookPayload:
        """Execute registered hooks for given hook_type sequentially.

        Returns:
            HookPayload containing updated payload data and cancellation status.
        """
        payload = HookPayload(
            hook_type=hook_type,
            plugin_id=plugin_id,
            data=initial_data or {},
        )

        hooks = self.registry.get_hooks(hook_type)
        for registered in hooks:
            if payload.cancelled:
                break
            try:
                await registered.handler(payload)
            except Exception as e:
                logger.error(
                    f"Hook handler execution failed for plugin '{registered.plugin_id}' on '{hook_type.value}': {e}"
                )

        return payload
