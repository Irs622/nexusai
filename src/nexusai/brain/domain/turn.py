"""
Turn, Message, and Conversation domain entities and aggregates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from nexusai.brain.domain.prompt import MessageRole


@dataclass
class Message:
    """Represents a single message utterance entity in conversation history.

    Attributes:
        id: Unique identifier for the message.
        role: Canonical role (SYSTEM, USER, ASSISTANT).
        content: Message content.
        metadata: Arbitrary metadata.
        timestamp: Creation timestamp.
    """

    id: UUID = field(default_factory=uuid4)
    role: MessageRole = MessageRole.USER
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Turn:
    """Represents a single request-response turn exchange.

    Attributes:
        id: Unique turn identifier.
        conversation_id: Logical conversation ID.
        user_message: Incoming user message utterance.
        assistant_message: Generated assistant response utterance (or None if incomplete).
        token_usage: Dictionary containing token breakdown (input, output, total).
        duration_ms: Total latency in milliseconds for the turn.
        status: Execution status (e.g. COMPLETED, FAILED, CANCELLED).
        created_at: Timestamp when turn started.
    """

    id: UUID = field(default_factory=uuid4)
    conversation_id: UUID = field(default_factory=uuid4)
    user_message: Message = field(default_factory=Message)
    assistant_message: Message | None = None
    token_usage: dict[str, int] = field(default_factory=dict)
    duration_ms: float = 0.0
    status: str = "PENDING"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Conversation:
    """Logical conversation aggregate root containing turn history.

    Attributes:
        id: Unique conversation identifier.
        turns: Ordered list of Turn exchanges.
        metadata: Conversation-level metadata.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    id: UUID = field(default_factory=uuid4)
    turns: list[Turn] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
