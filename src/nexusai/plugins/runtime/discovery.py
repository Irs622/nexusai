"""
PluginDiscoveryEngine for non-instantiating candidate discovery.
"""

from __future__ import annotations

from pathlib import Path
import sys

from nexusai.plugins.runtime.candidate import PluginCandidate


class PluginDiscoveryEngine:
    """Discovers plugin candidate locations without reading manifests or executing code."""

    def __init__(self, search_paths: list[Path] | None = None) -> None:
        self.search_paths = search_paths or []

    def add_search_path(self, path: Path) -> None:
        """Add filesystem directory path to candidate discovery list."""
        if path not in self.search_paths:
            self.search_paths.append(path)

    def discover_candidates(self) -> list[PluginCandidate]:
        """Scan configured search paths for plugin candidates.

        Returns:
            List of PluginCandidate descriptors.
        """
        candidates: list[PluginCandidate] = []
        seen_locations: set[Path] = set()

        for base_path in self.search_paths:
            if not base_path.exists() or not base_path.is_dir():
                continue

            # Check subdirectories for manifest files
            for entry in base_path.iterdir():
                if entry.is_dir():
                    loc = entry.resolve()
                    if loc in seen_locations:
                        continue

                    # Look for manifest candidate file
                    for manifest_file in ("plugin.yaml", "plugin.yml", "plugin.json"):
                        if (entry / manifest_file).exists():
                            seen_locations.add(loc)
                            fmt = manifest_file.split(".")[-1]
                            candidates.append(
                                PluginCandidate(
                                    id_hint=entry.name,
                                    location=loc,
                                    manifest_format=fmt,
                                )
                            )
                            break

        return candidates
