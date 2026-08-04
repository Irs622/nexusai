"""
Integration test running end-to-end plugin lifecycle pipeline.
"""

from pathlib import Path
import pytest

from nexusai.bus.bus import EventBus
from nexusai.plugins.contracts.base import BasePlugin
from nexusai.plugins.contracts.context import PluginContext
from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.contracts.state import PluginState
from nexusai.plugins.events.events import PluginStartedEvent
from nexusai.plugins.runtime.candidate import PluginCandidate
from nexusai.plugins.runtime.discovery import PluginDiscoveryEngine
from nexusai.plugins.runtime.lifecycle import PluginLifecycleManager
from nexusai.plugins.runtime.manifest_loader import ManifestLoader, MemorySource
from nexusai.plugins.runtime.registry import PluginRegistry
from nexusai.plugins.runtime.resolver import DependencyResolver
from nexusai.plugins.runtime.runtime import PluginRuntime
from nexusai.plugins.validation.validator import PluginValidator


class IntegrationCalculatorPlugin(BasePlugin):
    """Real calculator test plugin for end-to-end integration verification."""

    def __init__(self, manifest: PluginManifest, context: PluginContext) -> None:
        super().__init__(manifest, context)
        self.initialized = False
        self.started = False
        self.stopped = False

    async def on_initialize(self) -> None:
        self.initialized = True

    async def on_start(self) -> None:
        self.started = True

    async def on_stop(self) -> None:
        self.stopped = True

    def add(self, a: float, b: float) -> float:
        return a + b


@pytest.mark.asyncio
async def test_end_to_end_plugin_pipeline():
    # 1. Prepare Manifest & Virtual File
    manifest_yaml = """
id: org.nexusai.calculator
name: NexusAI Calculator Plugin
version: 1.0.0
entrypoint: tests.plugins.integration.test_end_to_end_pipeline:IntegrationCalculatorPlugin
capabilities:
  - tool.integration
permissions:
  filesystem:
    read:
      - /tmp
"""
    virtual_path = Path("/virtual/calculator/plugin.yaml")
    memory_source = MemorySource({virtual_path: (manifest_yaml, "yaml")})

    # 2. Manifest Loader & Validator
    loader = ManifestLoader(source=memory_source)
    manifest, raw_content = loader.load_manifest(virtual_path)

    validator = PluginValidator()
    validator.validate_manifest(manifest)

    # 3. Dependency Resolver
    resolver = DependencyResolver()
    plan = resolver.compute_loading_plan([manifest])
    assert plan.is_valid is True
    assert plan.order == ("org.nexusai.calculator",)

    # 4. Lifecycle Manager & Event Bus
    event_bus = EventBus()
    events_received: list[PluginStartedEvent] = []

    async def on_started(evt: PluginStartedEvent) -> None:
        events_received.append(evt)

    event_bus.subscribe(PluginStartedEvent, on_started)

    registry = PluginRegistry()
    runtime = PluginRuntime()
    lifecycle_mgr = PluginLifecycleManager(registry=registry, runtime=runtime, event_bus=event_bus)

    candidate = PluginCandidate(
        id_hint="calculator",
        location=virtual_path.parent,
        manifest_format="yaml",
    )

    # 5. Initialize & Start Plugin
    await lifecycle_mgr.initialize_and_start_plugin(candidate, manifest, raw_content)

    assert registry.get_state(manifest.id) == PluginState.ACTIVE
    instance = runtime.get_instance(manifest.id)
    assert isinstance(instance, IntegrationCalculatorPlugin)
    assert instance.initialized is True
    assert instance.started is True
    assert instance.add(10, 20) == 30.0

    # Verify event published via EventBus
    assert len(events_received) == 1
    assert events_received[0].plugin_id == "org.nexusai.calculator"

    # 6. Capability Resolution in Registry
    resolved = registry.resolve_first("tool.integration")
    assert resolved.id == "org.nexusai.calculator"

    # 7. Stop and Unload
    await lifecycle_mgr.stop_and_unload_plugin(manifest.id)
    assert registry.get_state(manifest.id) == PluginState.UNLOADED
    assert instance.stopped is True
