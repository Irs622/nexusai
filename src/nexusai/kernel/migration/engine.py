"""
Kernel Migration, MigrationPlan, and MigrationRunner abstract contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class SchemaVersion:
    """Schema version representation for records and data stores."""

    major: int = 1
    minor: int = 0
    patch: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class MigrationStep:
    """Descriptor for a single migration step."""

    name: str
    from_version: SchemaVersion
    to_version: SchemaVersion
    description: str = ""


@dataclass(frozen=True)
class MigrationPlan:
    """Sequenced list of migration steps."""

    target_version: SchemaVersion
    steps: tuple[MigrationStep, ...] = field(default_factory=tuple)


class MigrationRunner(ABC):
    """Abstract runner interface for executing schema migrations."""

    @abstractmethod
    async def get_current_version(self) -> SchemaVersion:
        """Return currently applied schema version."""
        pass

    @abstractmethod
    async def apply_migration(self, plan: MigrationPlan) -> SchemaVersion:
        """Apply migration plan and return new applied schema version."""
        pass
