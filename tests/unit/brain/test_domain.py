"""
Unit tests for nexusai.brain.domain models, invariants, polymorphism, and serialization boundaries.
"""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

from nexusai.brain.domain import (
    Artifact,
    AudioArtifact,
    BrainSession,
    Conversation,
    DocumentArtifact,
    ImageArtifact,
    Message,
    MessageRole,
    PromptBundle,
    PromptMessage,
    SchemaVersion,
    TextArtifact,
    Turn,
)
from nexusai.core.errors import BrainPromptRenderError, BrainProviderUnavailableError


def test_schema_version_compatibility_and_serialization() -> None:
    """Verify SchemaVersion logic, comparison, tuple/dict serialization."""
    v1_0 = SchemaVersion(1, 0)
    v1_2 = SchemaVersion(1, 2)
    v2_0 = SchemaVersion(2, 0)

    assert str(v1_0) == "1.0"
    assert v1_2.is_compatible_with(v1_0) is True
    assert v1_0.is_compatible_with(v1_2) is False
    assert v2_0.is_compatible_with(v1_0) is False
    assert v1_0.to_tuple() == (1, 0)

    d = v1_2.to_dict()
    assert d == {"major": 1, "minor": 2}
    deserialized = SchemaVersion.from_dict(d)
    assert deserialized == v1_2


def test_polymorphic_artifacts_interface() -> None:
    """Verify polymorphic Artifact interface methods (kind, size_bytes, validate, to_dict, from_dict)."""
    text_art = TextArtifact(text="Hello world", metadata={"lang": "en"})
    img_art = ImageArtifact(image_url_or_bytes="https://example.com/img.png", mime_type="image/png")
    audio_art = AudioArtifact(audio_bytes=b"\x00\x01\x02", sample_rate=16000)
    doc_art = DocumentArtifact(file_path_or_bytes="/tmp/doc.pdf", file_type="pdf")

    # Verify polymorphic kind() method
    assert text_art.kind() == "text"
    assert img_art.kind() == "image"
    assert audio_art.kind() == "audio"
    assert doc_art.kind() == "document"

    # Verify size_bytes() method
    assert text_art.size_bytes() == 11
    assert audio_art.size_bytes() == 3

    # Verify validate() method
    assert text_art.validate() is True
    assert img_art.validate() is True
    assert audio_art.validate() is True
    assert doc_art.validate() is True

    # Verify polymorphism via base class collection without isinstance branching
    artifacts: list[Artifact] = [text_art, img_art, audio_art, doc_art]
    total_size = sum(art.size_bytes() for art in artifacts)
    assert total_size > 0

    # Verify serialization boundary
    d = text_art.to_dict()
    deserialized = Artifact.from_dict(d)
    assert isinstance(deserialized, TextArtifact)
    assert deserialized.text == "Hello world"
    assert deserialized.kind() == "text"


def test_prompt_bundle_immutability_and_invariants() -> None:
    """Verify PromptBundle true immutability (tuple), constructor invariants, and serialization."""
    msg = PromptMessage(role=MessageRole.USER, content="Hello")
    bundle = PromptBundle(messages=[msg])  # Passed as list, converted to tuple in __post_init__

    assert isinstance(bundle.messages, tuple)
    assert len(bundle.messages) == 1
    assert bundle.bundle_version == SchemaVersion(1, 0)

    # Immutability check: cannot append to tuple
    with pytest.raises(AttributeError):
        bundle.messages.append(msg)  # type: ignore[attr-defined]

    # Invariant check: Empty bundle raises BrainPromptRenderError in __post_init__
    with pytest.raises(BrainPromptRenderError, match="bundle must contain at least one message"):
        PromptBundle(messages=(), artifacts=(), system_instruction=None)

    # Serialization check
    d = bundle.to_dict()
    restored = PromptBundle.from_dict(d)
    assert isinstance(restored.messages, tuple)
    assert restored.messages[0].content == "Hello"


def test_brain_session_serialization_and_immutability() -> None:
    """Verify BrainSession identity object immutability and dictionary serialization."""
    session = BrainSession(runtime_metadata={"tenant": "acme"})
    assert session.session_schema_version == SchemaVersion(1, 0)

    with pytest.raises(FrozenInstanceError):
        session.runtime_metadata = {"modified": True}  # type: ignore[misc]

    d = session.to_dict()
    restored = BrainSession.from_dict(d)
    assert restored.session_id == session.session_id
    assert restored.runtime_metadata == {"tenant": "acme"}


def test_turn_message_conversation() -> None:
    """Verify Conversation aggregate root, Turn, and Message entity initialization."""
    user_msg = Message(role=MessageRole.USER, content="Query")
    turn = Turn(user_message=user_msg, status="PENDING")
    conv = Conversation(turns=[turn])

    assert len(conv.turns) == 1
    assert conv.turns[0].user_message.content == "Query"
    assert turn.status == "PENDING"


def test_enriched_error_metadata() -> None:
    """Verify BrainProviderUnavailableError rich metadata instantiation."""
    err = BrainProviderUnavailableError(
        message="Service 503 Unavailable",
        provider_id="anthropic",
        status_code=503,
        retryable=True,
        request_id="req_999",
    )

    assert err.provider_id == "anthropic"
    assert err.status_code == 503
    assert err.retryable is True
    assert err.details["provider_id"] == "anthropic"
    assert err.details["retryable"] == "True"
