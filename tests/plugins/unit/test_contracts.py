"""
Unit tests for core plugin contracts and abstractions.
"""

import pytest

from nexusai.plugins.contracts import (
    PluginCapability,
    PluginCapabilityType,
    PluginContext,
    PluginManifest,
    PluginMetadata,
    PluginState,
)


def test_plugin_state_properties():
    assert PluginState.ACTIVE.is_active() is True
    assert PluginState.STOPPED.is_active() is False
    assert PluginState.UNLOADED.is_terminal() is True
    assert PluginState.FAILED.is_terminal() is True
    assert PluginState.ACTIVE.is_terminal() is False


def test_plugin_capability_formatting():
    cap = PluginCapability.LLM_PROVIDER
    assert cap.name == PluginCapabilityType.LLM_PROVIDER.value
    assert str(cap) == "llm.provider:1.0.0"

    custom = PluginCapability.custom("my.custom", "2.1.0")
    assert str(custom) == "my.custom:2.1.0"


def test_plugin_metadata_creation():
    meta = PluginMetadata(
        id="org.nexusai.test",
        name="Test Plugin",
        version="1.0.0",
        author="Nexus Core",
        description="A test plugin",
    )
    assert meta.id == "org.nexusai.test"
    assert meta.name == "Test Plugin"


def test_plugin_manifest_defaults():
    manifest = PluginManifest(
        id="org.nexusai.dummy",
        name="Dummy",
        version="0.1.0",
        entrypoint="dummy_mod:DummyPlugin",
    )
    assert manifest.id == "org.nexusai.dummy"
    assert manifest.kernel_api == 1
    assert manifest.plugin_api == 1
    assert manifest.minimum_kernel == "0.1.0"


def test_plugin_context_immutability():
    ctx = PluginContext(
        plugin_id="test.id",
        logger=None,
        sandbox=None,
        config_slice={"key": "val"},
    )
    assert ctx.plugin_id == "test.id"
    with pytest.raises(Exception):
        ctx.plugin_id = "new.id"
