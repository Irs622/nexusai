"""
Unit tests for PluginRegistry and PluginDescriptor capability resolution.
"""

from pathlib import Path
import pytest

from nexusai.plugins.contracts.capability import PluginCapability
from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.contracts.state import PluginState
from nexusai.plugins.exceptions import PluginResolutionError
from nexusai.plugins.runtime.descriptor import PluginDescriptor
from nexusai.plugins.runtime.registry import PluginRegistry


def test_registry_registration_and_lookup():
    registry = PluginRegistry()
    manifest = PluginManifest(
        id="org.nexusai.llm.openrouter",
        name="OpenRouter LLM",
        version="1.0.0",
        entrypoint="mod:Class",
        capabilities=["llm.provider"],
    )
    descriptor = PluginDescriptor(
        id=manifest.id,
        manifest=manifest,
        manifest_checksum="abc",
        plugin_checksum="abc",
        location=Path("/tmp/plugin"),
    )

    registry.register(descriptor, initial_state=PluginState.LOADED)
    assert registry.exists(manifest.id) is True
    assert registry.get_state(manifest.id) == PluginState.LOADED


def test_registry_capability_resolution():
    registry = PluginRegistry()
    manifest1 = PluginManifest(
        id="llm.provider1",
        name="LLM 1",
        version="1.0.0",
        entrypoint="mod:Class",
        capabilities=["llm.provider"],
    )
    manifest2 = PluginManifest(
        id="vector.provider1",
        name="Vector 1",
        version="1.0.0",
        entrypoint="mod:Class",
        capabilities=["vector.store"],
    )

    desc1 = PluginDescriptor(id=manifest1.id, manifest=manifest1, manifest_checksum="1", plugin_checksum="1", location=Path("/t1"))
    desc2 = PluginDescriptor(id=manifest2.id, manifest=manifest2, manifest_checksum="2", plugin_checksum="2", location=Path("/t2"))

    registry.register(desc1)
    registry.register(desc2)

    llm_matches = registry.resolve_capability(PluginCapability.LLM_PROVIDER)
    assert len(llm_matches) == 1
    assert llm_matches[0].id == "llm.provider1"

    first_llm = registry.resolve_first("llm.provider")
    assert first_llm.id == "llm.provider1"

    with pytest.raises(PluginResolutionError):
        registry.resolve_first("stt.provider")
