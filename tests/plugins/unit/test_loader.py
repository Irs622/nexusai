"""
Unit tests for PluginLoader module import and class instantiation.
"""

from pathlib import Path
import pytest

from nexusai.plugins.contracts.base import BasePlugin
from nexusai.plugins.contracts.context import PluginContext
from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.exceptions import PluginLoadError
from nexusai.plugins.runtime.loader import PluginLoader
from nexusai.plugins.runtime.sandbox import PluginSandbox
from nexusai.plugins.security import PermissionEnforcer, ScopedPermissions


class MockTestPlugin(BasePlugin):
    """Mock plugin implementation for testing PluginLoader."""

    def __init__(self, manifest: PluginManifest, context: PluginContext) -> None:
        super().__init__(manifest, context)
        self.started = False

    async def on_start(self) -> None:
        self.started = True


def test_plugin_loader_success():
    loader = PluginLoader()
    manifest = PluginManifest(
        id="mock.plugin",
        name="Mock Plugin",
        version="1.0.0",
        entrypoint="tests.plugins.unit.test_loader:MockTestPlugin",
    )
    context = PluginContext(
        plugin_id=manifest.id,
        logger=None,
        sandbox=PluginSandbox(PermissionEnforcer(ScopedPermissions())),
    )

    instance = loader.load_plugin_instance(manifest, context)
    assert isinstance(instance, BasePlugin)
    assert instance.plugin_id == "mock.plugin"


def test_plugin_loader_invalid_class_raises():
    loader = PluginLoader()
    manifest = PluginManifest(
        id="mock.invalid",
        name="Mock Invalid",
        version="1.0.0",
        entrypoint="tests.plugins.unit.test_loader:NonExistentClass",
    )
    context = PluginContext(
        plugin_id=manifest.id,
        logger=None,
        sandbox=PluginSandbox(PermissionEnforcer(ScopedPermissions())),
    )

    with pytest.raises(PluginLoadError):
        loader.load_plugin_instance(manifest, context)
