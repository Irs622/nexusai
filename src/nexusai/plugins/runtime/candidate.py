"""
PluginCandidate representation for non-instantiating discovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PluginCandidate:
    """Represents a discovered candidate plugin location prior to reading manifest."""

    id_hint: str
    location: Path
    manifest_format: str = "yaml"
