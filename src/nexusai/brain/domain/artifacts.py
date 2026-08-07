"""
Polymorphic Artifact abstractions for multimodal inputs and outputs in PromptBundle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Type
from uuid import UUID, uuid4


@dataclass(frozen=True)
class Artifact(ABC):
    """Abstract base class for all polymorphic input and output artifacts.

    Attributes:
        artifact_id: Unique UUID identifier for the artifact instance.
        metadata: Arbitrary key-value metadata associated with the artifact.
    """

    artifact_id: UUID = field(default_factory=uuid4)
    metadata: dict[str, Any] = field(default_factory=dict)

    @abstractmethod
    def kind(self) -> str:
        """Return the polymorphic artifact discriminator string (e.g. 'text', 'image')."""
        ...

    @abstractmethod
    def size_bytes(self) -> int:
        """Return the estimated payload size of the artifact in bytes."""
        ...

    @abstractmethod
    def validate(self) -> bool:
        """Validate artifact internal consistency."""
        ...

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize artifact to dictionary representation."""
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Artifact:
        """Deserialize dictionary representation using the ArtifactRegistry."""
        kind = str(data.get("kind", "text"))
        return ArtifactRegistry.deserialize(kind, data)


class ArtifactRegistry:
    """Extensible registry mapping artifact kind strings to factory deserializers."""

    _registry: dict[str, Callable[[dict[str, Any]], Artifact]] = {}

    @classmethod
    def register(cls, kind: str, factory: Callable[[dict[str, Any]], Artifact]) -> None:
        """Register a deserializer factory for a specific artifact kind string."""
        cls._registry[kind] = factory

    @classmethod
    def deserialize(cls, kind: str, data: dict[str, Any]) -> Artifact:
        """Deserialize payload data using the registered factory for kind."""
        if kind not in cls._registry:
            raise ValueError(f"Unknown or unregistered artifact kind: '{kind}'")
        return cls._registry[kind](data)


@dataclass(frozen=True)
class TextArtifact(Artifact):
    """Represents a text utterance or text document artifact."""

    text: str = ""

    def kind(self) -> str:
        return "text"

    def size_bytes(self) -> int:
        return len(self.text.encode("utf-8"))

    def validate(self) -> bool:
        return isinstance(self.text, str)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind(),
            "artifact_id": str(self.artifact_id),
            "text": self.text,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict_factory(cls, data: dict[str, Any]) -> TextArtifact:
        artifact_id = UUID(data["artifact_id"]) if "artifact_id" in data else uuid4()
        return cls(
            artifact_id=artifact_id,
            metadata=dict(data.get("metadata", {})),
            text=str(data.get("text", "")),
        )


@dataclass(frozen=True)
class ImageArtifact(Artifact):
    """Represents an image payload (URL or raw bytes)."""

    image_url_or_bytes: str | bytes | None = None
    mime_type: str = "image/png"

    def kind(self) -> str:
        return "image"

    def size_bytes(self) -> int:
        if isinstance(self.image_url_or_bytes, bytes):
            return len(self.image_url_or_bytes)
        if isinstance(self.image_url_or_bytes, str):
            return len(self.image_url_or_bytes.encode("utf-8"))
        return 0

    def validate(self) -> bool:
        return self.image_url_or_bytes is not None and len(self.mime_type) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind(),
            "artifact_id": str(self.artifact_id),
            "image_url_or_bytes": self.image_url_or_bytes if isinstance(self.image_url_or_bytes, str) else None,
            "mime_type": self.mime_type,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict_factory(cls, data: dict[str, Any]) -> ImageArtifact:
        artifact_id = UUID(data["artifact_id"]) if "artifact_id" in data else uuid4()
        return cls(
            artifact_id=artifact_id,
            metadata=dict(data.get("metadata", {})),
            image_url_or_bytes=data.get("image_url_or_bytes"),
            mime_type=str(data.get("mime_type", "image/png")),
        )


@dataclass(frozen=True)
class AudioArtifact(Artifact):
    """Represents an audio payload (raw PCM/WAV/MP3 bytes)."""

    audio_bytes: bytes = b""
    sample_rate: int = 16000

    def kind(self) -> str:
        return "audio"

    def size_bytes(self) -> int:
        return len(self.audio_bytes)

    def validate(self) -> bool:
        return self.sample_rate > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind(),
            "artifact_id": str(self.artifact_id),
            "audio_bytes": self.audio_bytes,
            "sample_rate": self.sample_rate,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict_factory(cls, data: dict[str, Any]) -> AudioArtifact:
        artifact_id = UUID(data["artifact_id"]) if "artifact_id" in data else uuid4()
        raw_audio = data.get("audio_bytes", b"")
        audio_bytes = raw_audio if isinstance(raw_audio, bytes) else str(raw_audio).encode("utf-8")
        return cls(
            artifact_id=artifact_id,
            metadata=dict(data.get("metadata", {})),
            audio_bytes=audio_bytes,
            sample_rate=int(data.get("sample_rate", 16000)),
        )


@dataclass(frozen=True)
class DocumentArtifact(Artifact):
    """Represents a generic file or document attachment (PDF, TXT, CSV, etc.)."""

    file_path_or_bytes: str | bytes | None = None
    file_type: str = "pdf"

    def kind(self) -> str:
        return "document"

    def size_bytes(self) -> int:
        if isinstance(self.file_path_or_bytes, bytes):
            return len(self.file_path_or_bytes)
        if isinstance(self.file_path_or_bytes, str):
            return len(self.file_path_or_bytes.encode("utf-8"))
        return 0

    def validate(self) -> bool:
        return self.file_path_or_bytes is not None and len(self.file_type) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind(),
            "artifact_id": str(self.artifact_id),
            "file_path_or_bytes": self.file_path_or_bytes if isinstance(self.file_path_or_bytes, str) else None,
            "file_type": self.file_type,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict_factory(cls, data: dict[str, Any]) -> DocumentArtifact:
        artifact_id = UUID(data["artifact_id"]) if "artifact_id" in data else uuid4()
        return cls(
            artifact_id=artifact_id,
            metadata=dict(data.get("metadata", {})),
            file_path_or_bytes=data.get("file_path_or_bytes"),
            file_type=str(data.get("file_type", "pdf")),
        )


# Register default concrete artifact factories
ArtifactRegistry.register("text", TextArtifact.from_dict_factory)
ArtifactRegistry.register("image", ImageArtifact.from_dict_factory)
ArtifactRegistry.register("audio", AudioArtifact.from_dict_factory)
ArtifactRegistry.register("document", DocumentArtifact.from_dict_factory)
