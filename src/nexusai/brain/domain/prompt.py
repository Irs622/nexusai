"""
Canonical PromptBundle and PromptMessage domain value objects with serialization boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nexusai.brain.domain.artifacts import Artifact
from nexusai.brain.domain.version import SchemaVersion
from nexusai.core.errors import BrainPromptRenderError


class MessageRole(str, Enum):
    """Canonical message role enumeration."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class PromptMessage:
    """Represents an individual message in a canonical prompt bundle.

    Attributes:
        role: The role of the speaker (SYSTEM, USER, ASSISTANT).
        content: The text content of the message utterance.
        metadata: Additional message-level metadata.
    """

    role: MessageRole
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize PromptMessage to dictionary format."""
        return {
            "role": self.role.value,
            "content": self.content,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptMessage:
        """Deserialize PromptMessage from dictionary format."""
        return cls(
            role=MessageRole(data.get("role", "user")),
            content=str(data.get("content", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class PromptBundle:
    """Immutable provider-independent prompt container passed to ProviderRuntime adapters.

    Attributes:
        bundle_version: Contract schema versioning.
        system_instruction: Optional explicit system prompt instruction.
        messages: Immutable tuple of canonical prompt messages.
        artifacts: Immutable tuple of polymorphic attachments (images, audio, files).
        options: Generation or formatting options.
    """

    bundle_version: SchemaVersion = field(default_factory=SchemaVersion)
    system_instruction: str | None = None
    messages: tuple[PromptMessage, ...] = field(default_factory=tuple)
    artifacts: tuple[Artifact, ...] = field(default_factory=tuple)
    options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Enforce domain invariants for PromptBundle."""
        # Convert list to tuple if passed as list during initialization
        if isinstance(self.messages, list):
            object.__setattr__(self, "messages", tuple(self.messages))
        if isinstance(self.artifacts, list):
            object.__setattr__(self, "artifacts", tuple(self.artifacts))

        if not self.messages and not self.artifacts and not self.system_instruction:
            raise BrainPromptRenderError(
                "PromptBundle invariant violated: bundle must contain at least one message, artifact, or system instruction."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize PromptBundle to dictionary format for persistence or network boundaries."""
        return {
            "bundle_version": self.bundle_version.to_dict(),
            "system_instruction": self.system_instruction,
            "messages": [msg.to_dict() for msg in self.messages],
            "artifacts": [art.to_dict() for art in self.artifacts],
            "options": self.options,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptBundle:
        """Deserialize PromptBundle from dictionary format."""
        version_data = data.get("bundle_version", {})
        bundle_version = (
            SchemaVersion.from_dict(version_data)
            if isinstance(version_data, dict)
            else SchemaVersion()
        )

        messages = tuple(PromptMessage.from_dict(m) for m in data.get("messages", []))
        artifacts = tuple(Artifact.from_dict(a) for a in data.get("artifacts", []))

        return cls(
            bundle_version=bundle_version,
            system_instruction=data.get("system_instruction"),
            messages=messages,
            artifacts=artifacts,
            options=dict(data.get("options", {})),
        )
