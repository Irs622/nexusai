"""
SchemaVersion definition for versioned domain and transport contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SchemaVersion:
    """Represents major and minor schema versions for public contracts.

    Attributes:
        major: Major version number (breaking changes).
        minor: Minor version number (backward-compatible additions).
    """

    major: int = 1
    minor: int = 0

    def is_compatible_with(self, other: SchemaVersion) -> bool:
        """Check backward compatibility with another schema version."""
        return self.major == other.major and self.minor >= other.minor

    def supports(self, required_version: SchemaVersion) -> bool:
        """Explicit semantic check: evaluates if this current schema version supports the required version."""
        return self.is_compatible_with(required_version)

    def can_read(self, version: SchemaVersion) -> bool:
        """Explicit semantic check: evaluates if this current schema version can read target version."""
        return self.major == version.major and self.minor >= version.minor

    def to_tuple(self) -> tuple[int, int]:
        """Return version as a (major, minor) integer tuple."""
        return (self.major, self.minor)

    def to_dict(self) -> dict[str, int]:
        """Serialize version to dictionary representation."""
        return {"major": self.major, "minor": self.minor}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SchemaVersion:
        """Deserialize version from dictionary representation."""
        return cls(
            major=int(data.get("major", 1)),
            minor=int(data.get("minor", 0)),
        )

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}"
