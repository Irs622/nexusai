"""
Plugin metadata dataclass definition.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PluginMetadata:
    """Canonical plugin metadata container."""

    id: str
    name: str
    version: str
    author: str
    description: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    homepage: str = ""
    repository: str = ""
    license: str = "MIT"
