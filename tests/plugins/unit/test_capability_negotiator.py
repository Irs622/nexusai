"""
Unit tests for CapabilityNegotiator constraint matching.
"""

from pathlib import Path

from nexusai.plugins.contracts.capability import PluginCapability
from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.runtime.capability_negotiator import CapabilityNegotiator
from nexusai.plugins.runtime.descriptor import PluginDescriptor
from nexusai.plugins.runtime.registry import PluginRegistry


def test_capability_negotiator_with_constraints():
    registry = PluginRegistry()

    m1 = PluginManifest(
        id="llm.streaming",
        name="Streaming LLM",
        version="1.0.0",
        entrypoint="mod:Class",
        capabilities=["llm.provider"],
        permissions={"supports_stream": True},
    )
    m2 = PluginManifest(
        id="llm.sync",
        name="Sync LLM",
        version="1.0.0",
        entrypoint="mod:Class",
        capabilities=["llm.provider"],
        permissions={"supports_stream": False},
    )

    registry.register(PluginDescriptor(id=m1.id, manifest=m1, manifest_checksum="1", plugin_checksum="1", location=Path("/t1")))
    registry.register(PluginDescriptor(id=m2.id, manifest=m2, manifest_checksum="2", plugin_checksum="2", location=Path("/t2")))

    negotiator = CapabilityNegotiator(registry)
    matches = negotiator.negotiate(PluginCapability.LLM_PROVIDER, {"supports_stream": True})

    assert len(matches) == 1
    assert matches[0].id == "llm.streaming"
