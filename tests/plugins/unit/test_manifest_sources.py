"""
Unit tests for ManifestLoader and ManifestSource implementations.
"""

from pathlib import Path

import pytest

from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.exceptions import PluginManifestError
from nexusai.plugins.runtime.manifest_loader import ManifestLoader, MemorySource


def test_memory_source_yaml_manifest_loading():
    yaml_content = """
id: org.nexusai.memory_test
name: Memory Test Plugin
version: 1.0.0
entrypoint: module:PluginClass
capabilities:
  - llm.provider
"""
    p = Path("/virtual/plugin.yaml")
    source = MemorySource({p: (yaml_content, "yaml")})
    loader = ManifestLoader(source=source)

    manifest, raw = loader.load_manifest(p)
    assert isinstance(manifest, PluginManifest)
    assert manifest.id == "org.nexusai.memory_test"
    assert "llm.provider" in manifest.capabilities


def test_memory_source_json_manifest_loading():
    json_content = """{
        "id": "org.nexusai.json_test",
        "name": "JSON Test Plugin",
        "version": "2.0.0",
        "entrypoint": "json_module:PluginClass"
    }"""
    p = Path("/virtual/plugin.json")
    source = MemorySource({p: (json_content, "json")})
    loader = ManifestLoader(source=source)

    manifest, raw = loader.load_manifest(p)
    assert manifest.id == "org.nexusai.json_test"
    assert manifest.version == "2.0.0"


def test_invalid_manifest_content_raises_error():
    p = Path("/virtual/invalid.yaml")
    source = MemorySource({p: ("invalid: [yaml: broken", "yaml")})
    loader = ManifestLoader(source=source)

    with pytest.raises(PluginManifestError):
        loader.load_manifest(p)
