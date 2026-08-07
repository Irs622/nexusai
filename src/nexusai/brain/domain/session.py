"""
BrainSession domain aggregate root representing immutable session identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from nexusai.brain.domain.version import SchemaVersion


@dataclass(frozen=True)
class BrainSession:
    """Immutable identity context for an execution session across turns.

    Attributes:
        session_id: Unique UUID identifier for this session.
        conversation_id: Unique UUID identifier for the target conversation history boundary.
        session_schema_version: Schema version of the session contract.
        created_at: UTC timestamp when the session was initialized.
        runtime_metadata: Static session metadata (user info, app tag, etc.).
    """

    session_id: UUID = field(default_factory=uuid4)
    conversation_id: UUID = field(default_factory=uuid4)
    session_schema_version: SchemaVersion = field(default_factory=SchemaVersion)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    runtime_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize BrainSession to dictionary format."""
        return {
            "session_id": str(self.session_id),
            "conversation_id": str(self.conversation_id),
            "session_schema_version": self.session_schema_version.to_dict(),
            "created_at": self.created_at.isoformat(),
            "runtime_metadata": self.runtime_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrainSession:
        """Deserialize BrainSession from dictionary format."""
        version_data = data.get("session_schema_version", {})
        schema_version = (
            SchemaVersion.from_dict(version_data) if isinstance(version_data, dict) else SchemaVersion()
        )
        created_at_val = data.get("created_at")
        created_at = datetime.fromisoformat(created_at_val) if isinstance(created_at_val, str) else datetime.now(timezone.utc)

        return cls(
            session_id=UUID(data["session_id"]) if "session_id" in data else uuid4(),
            conversation_id=UUID(data["conversation_id"]) if "conversation_id" in data else uuid4(),
            session_schema_version=schema_version,
            created_at=created_at,
            runtime_metadata=dict(data.get("runtime_metadata", {})),
        )
