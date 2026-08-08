"""
Multi-format ManifestLoader and ManifestSource abstractions.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml

from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.exceptions import PluginManifestError


class ManifestSource(ABC):
    """Abstract source interface for manifest content."""

    @abstractmethod
    def read_manifest_content(self, location: Path) -> tuple[str, str]:
        """Return (raw_content_str, format_ext)."""
        pass


class FilesystemSource(ManifestSource):
    """Reads manifest files from local filesystem."""

    def read_manifest_content(self, location: Path) -> tuple[str, str]:
        if location.is_dir():
            for candidate in ("plugin.yaml", "plugin.yml", "plugin.json", "plugin.toml"):
                p = location / candidate
                if p.exists():
                    ext = p.suffix.lstrip(".")
                    with open(p, "r", encoding="utf-8") as f:
                        return f.read(), ext
            raise PluginManifestError(f"No manifest file found in directory '{location}'")
        elif location.is_file():
            ext = location.suffix.lstrip(".")
            with open(location, "r", encoding="utf-8") as f:
                return f.read(), ext
        raise PluginManifestError(f"Manifest location '{location}' does not exist")


class MemorySource(ManifestSource):
    """Reads manifest files from memory dict/string mapping."""

    def __init__(self, content_map: dict[Path, tuple[str, str]]) -> None:
        self.content_map = content_map

    def read_manifest_content(self, location: Path) -> tuple[str, str]:
        if location in self.content_map:
            return self.content_map[location]
        raise PluginManifestError(f"Manifest location '{location}' not found in memory source")


class ManifestReader(ABC):
    """Abstract manifest format reader."""

    @abstractmethod
    def parse(self, raw_content: str) -> dict[str, Any]:
        """Parse raw content into dict."""
        pass


class YAMLManifestReader(ManifestReader):
    """YAML manifest format reader."""

    def parse(self, raw_content: str) -> dict[str, Any]:
        try:
            data = yaml.safe_load(raw_content)
            if not isinstance(data, dict):
                raise PluginManifestError("Parsed YAML manifest is not a valid dictionary")
            return data
        except Exception as e:
            raise PluginManifestError(f"Failed to parse YAML manifest: {e}") from e


class JSONManifestReader(ManifestReader):
    """JSON manifest format reader."""

    def parse(self, raw_content: str) -> dict[str, Any]:
        try:
            data = json.loads(raw_content)
            if not isinstance(data, dict):
                raise PluginManifestError("Parsed JSON manifest is not a valid dictionary")
            return data
        except Exception as e:
            raise PluginManifestError(f"Failed to parse JSON manifest: {e}") from e


class ManifestLoader:
    """Loader orchestrating ManifestSource and ManifestReaders."""

    def __init__(self, source: ManifestSource | None = None) -> None:
        self.source = source or FilesystemSource()
        self.readers: dict[str, ManifestReader] = {
            "yaml": YAMLManifestReader(),
            "yml": YAMLManifestReader(),
            "json": JSONManifestReader(),
        }

    def load_manifest(self, location: Path) -> tuple[PluginManifest, str]:
        """Load and parse PluginManifest from location.

        Returns:
            Tuple of (PluginManifest, raw_content_str).
        """
        content, fmt = self.source.read_manifest_content(location)
        fmt = fmt.lower()
        if fmt not in self.readers:
            raise PluginManifestError(
                f"Unsupported manifest format '{fmt}' for location '{location}'"
            )

        data = self.readers[fmt].parse(content)
        try:
            manifest = PluginManifest(**data)
            return manifest, content
        except Exception as e:
            raise PluginManifestError(
                f"Manifest schema validation failed for '{location}': {e}"
            ) from e
