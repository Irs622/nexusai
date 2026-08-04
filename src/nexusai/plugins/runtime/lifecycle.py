"""
PluginLifecycleManager orchestrating 10-state lifecycle machine and event publishing.
"""

from __future__ import annotations

import logging
from typing import Any

from nexusai.bus.bus import EventBus
from nexusai.logging.logger import logger
from nexusai.plugins.contracts.context import PluginContext
from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.contracts.state import PluginState
from nexusai.plugins.events.events import (
    PluginDiscoveredEvent,
    PluginFailedEvent,
    PluginLoadedEvent,
    PluginStartedEvent,
    PluginStoppedEvent,
)
from nexusai.plugins.exceptions import PluginLifecycleError
from nexusai.plugins.runtime.candidate import PluginCandidate
from nexusai.plugins.runtime.descriptor import PluginDescriptor
from nexusai.plugins.runtime.loader import PluginLoader
from nexusai.plugins.runtime.registry import PluginRegistry
from nexusai.plugins.runtime.runtime import PluginRuntime
from nexusai.plugins.runtime.sandbox import PluginSandbox
from nexusai.plugins.security.permissions import PermissionEnforcer, ScopedPermissions
from nexusai.plugins.security.signatures import PluginSignatureVerifier


class PluginLifecycleManager:
    """Orchestrates plugin lifecycle state transitions, context injection, and event publishing."""

    def __init__(
        self,
        registry: PluginRegistry | None = None,
        runtime: PluginRuntime | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.registry = registry or PluginRegistry()
        self.runtime = runtime or PluginRuntime()
        self.event_bus = event_bus or EventBus()
        self.loader = PluginLoader()

    async def initialize_and_start_plugin(
        self,
        candidate: PluginCandidate,
        manifest: PluginManifest,
        raw_manifest_content: str,
    ) -> None:
        """Run full pipeline: Candidate → Parse → Validate → Load → Initialize → Start → ACTIVE."""
        plugin_id = manifest.id

        try:
            # 1. State: DISCOVERED
            self.registry.set_state(plugin_id, PluginState.DISCOVERED)
            if self.event_bus:
                await self.event_bus.publish(
                    PluginDiscoveredEvent(
                        plugin_id=plugin_id,
                        location=str(candidate.location),
                        manifest_format=candidate.manifest_format,
                    )
                )

            # 2. State: PARSED & VALIDATED
            self.registry.set_state(plugin_id, PluginState.VALIDATED)

            # 3. Create Descriptor
            checksum = PluginSignatureVerifier.calculate_manifest_checksum(raw_manifest_content)
            descriptor = PluginDescriptor(
                id=plugin_id,
                manifest=manifest,
                manifest_checksum=checksum,
                plugin_checksum=checksum,
                location=candidate.location,
            )
            self.registry.register(descriptor, initial_state=PluginState.VALIDATED)

            # 4. State: RESOLVED
            self.registry.set_state(plugin_id, PluginState.RESOLVED)

            # 5. Prepare Sandboxed Context
            permissions = ScopedPermissions.from_dict(manifest.permissions)
            enforcer = PermissionEnforcer(permissions)
            sandbox = PluginSandbox(enforcer)
            context = PluginContext(
                plugin_id=plugin_id,
                logger=logger,
                sandbox=sandbox,
                event_bus=self.event_bus,
            )

            # 6. State: LOADED (Instantiate plugin)
            instance = self.loader.load_plugin_instance(manifest, context, candidate.location)
            self.runtime.attach_instance(plugin_id, instance)
            await instance.on_load()
            self.registry.set_state(plugin_id, PluginState.LOADED)
            if self.event_bus:
                await self.event_bus.publish(
                    PluginLoadedEvent(
                        plugin_id=plugin_id,
                        version=manifest.version,
                        capabilities=manifest.capabilities,
                    )
                )

            # 7. State: INITIALIZED
            await instance.on_initialize()
            self.registry.set_state(plugin_id, PluginState.INITIALIZED)

            # 8. State: ACTIVE (Start plugin)
            await instance.on_start()
            self.registry.set_state(plugin_id, PluginState.ACTIVE)
            if self.event_bus:
                await self.event_bus.publish(
                    PluginStartedEvent(
                        plugin_id=plugin_id,
                        capabilities=manifest.capabilities,
                    )
                )

        except Exception as e:
            self.registry.set_state(plugin_id, PluginState.FAILED)
            if self.event_bus:
                await self.event_bus.publish(
                    PluginFailedEvent(
                        plugin_id=plugin_id,
                        error=str(e),
                        failed_state=PluginState.FAILED,
                    )
                )
            raise PluginLifecycleError(f"Lifecycle execution failed for plugin '{plugin_id}': {e}") from e

    async def stop_and_unload_plugin(self, plugin_id: str) -> None:
        """Stop and unload an active plugin."""
        instance = self.runtime.get_instance(plugin_id)
        if not instance:
            return

        try:
            # 1. State: STOPPED
            await instance.on_stop()
            self.registry.set_state(plugin_id, PluginState.STOPPED)
            if self.event_bus:
                await self.event_bus.publish(PluginStoppedEvent(plugin_id=plugin_id))

            # 2. State: UNLOADED
            await instance.on_unload()
            self.runtime.detach_instance(plugin_id)
            self.registry.set_state(plugin_id, PluginState.UNLOADED)

        except Exception as e:
            self.registry.set_state(plugin_id, PluginState.FAILED)
            if self.event_bus:
                await self.event_bus.publish(
                    PluginFailedEvent(
                        plugin_id=plugin_id,
                        error=str(e),
                        failed_state=PluginState.FAILED,
                    )
                )
            raise PluginLifecycleError(f"Failed to stop/unload plugin '{plugin_id}': {e}") from e
