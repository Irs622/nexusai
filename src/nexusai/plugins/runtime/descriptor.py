"""
Immutable PluginDescriptor record for registry metadata indexing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nexusai.plugins.contracts.manifest import PluginManifest


@dataclass(frozen=True)
class PluginDescriptor:
    """Immutable metadata record tracking plugin manifest and checksums."""

    id: str
    manifest: PluginManifest
    manifest_checksum: str
    plugin_checksum: str
    location: Path
