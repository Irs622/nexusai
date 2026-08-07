"""
ContextBudget and AssembledContext domain value objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexusai.brain.domain.prompt import PromptMessage
from nexusai.brain.domain.version import SchemaVersion
from nexusai.core.errors import BrainContextAssemblyError


@dataclass(frozen=True)
class ContextBudget:
    """Token budget configuration contract directing history loading and context assembly bounds.

    Attributes:
        max_input_tokens: Total token window size allocated for the model prompt.
        reserved_output_tokens: Reserved token headroom for model output generation.
        reserved_system_tokens: Reserved token headroom for system prompts.
        reserved_tool_tokens: Reserved token headroom for tool definitions/schemas.
        reserved_reasoning_tokens: Reserved token headroom for model reasoning/thinking tokens.
    """

    max_input_tokens: int = 128000
    reserved_output_tokens: int = 4096
    reserved_system_tokens: int = 512
    reserved_tool_tokens: int = 0
    reserved_reasoning_tokens: int = 0

    def __post_init__(self) -> None:
        """Enforce domain invariants for ContextBudget."""
        if self.max_input_tokens <= 0:
            raise BrainContextAssemblyError(
                f"ContextBudget invariant violated: max_input_tokens ({self.max_input_tokens}) must be positive."
            )
        if self.available_history_tokens <= 0:
            raise BrainContextAssemblyError(
                f"ContextBudget invariant violated: available_history_tokens ({self.available_history_tokens}) "
                "must be positive. Reserved tokens exceed max_input_tokens."
            )

    @property
    def available_history_tokens(self) -> int:
        """Calculate net token budget available for conversation history turns."""
        return (
            self.max_input_tokens
            - self.reserved_output_tokens
            - self.reserved_system_tokens
            - self.reserved_tool_tokens
            - self.reserved_reasoning_tokens
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize ContextBudget to dictionary format."""
        return {
            "max_input_tokens": self.max_input_tokens,
            "reserved_output_tokens": self.reserved_output_tokens,
            "reserved_system_tokens": self.reserved_system_tokens,
            "reserved_tool_tokens": self.reserved_tool_tokens,
            "reserved_reasoning_tokens": self.reserved_reasoning_tokens,
            "available_history_tokens": self.available_history_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextBudget:
        """Deserialize ContextBudget from dictionary format."""
        return cls(
            max_input_tokens=int(data.get("max_input_tokens", 128000)),
            reserved_output_tokens=int(data.get("reserved_output_tokens", 4096)),
            reserved_system_tokens=int(data.get("reserved_system_tokens", 512)),
            reserved_tool_tokens=int(data.get("reserved_tool_tokens", 0)),
            reserved_reasoning_tokens=int(data.get("reserved_reasoning_tokens", 0)),
        )


@dataclass(frozen=True)
class AssembledContext:
    """Immutable assembled context window payload ready for PromptRenderer processing.

    Attributes:
        context_version: Schema contract version.
        system_instruction: Resolved active system prompt instruction.
        history_messages: Tuple of truncated historical turn messages.
        user_message: Current incoming user prompt message.
        estimated_total_tokens: Estimated total token count of the assembled context (for budgeting).
        truncated_turn_count: Number of turns truncated to fit within budget limits.
        metadata: Assembled context metadata.
    """

    context_version: SchemaVersion = field(default_factory=SchemaVersion)
    system_instruction: str | None = None
    history_messages: tuple[PromptMessage, ...] = field(default_factory=tuple)
    user_message: PromptMessage = field(default_factory=lambda: PromptMessage(role="user", content=""))  # type: ignore[arg-type]
    estimated_total_tokens: int = 0
    truncated_turn_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Ensure tuple immutability for history_messages."""
        if isinstance(self.history_messages, list):
            object.__setattr__(self, "history_messages", tuple(self.history_messages))

    def to_dict(self) -> dict[str, Any]:
        """Serialize AssembledContext to dictionary format."""
        return {
            "context_version": self.context_version.to_dict(),
            "system_instruction": self.system_instruction,
            "history_messages": [m.to_dict() for m in self.history_messages],
            "user_message": self.user_message.to_dict(),
            "estimated_total_tokens": self.estimated_total_tokens,
            "truncated_turn_count": self.truncated_turn_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssembledContext:
        """Deserialize AssembledContext from dictionary format."""
        version_data = data.get("context_version", {})
        context_version = SchemaVersion.from_dict(version_data) if isinstance(version_data, dict) else SchemaVersion()
        history_messages = tuple(PromptMessage.from_dict(m) for m in data.get("history_messages", []))
        user_msg_data = data.get("user_message", {"role": "user", "content": ""})
        user_message = PromptMessage.from_dict(user_msg_data)

        return cls(
            context_version=context_version,
            system_instruction=data.get("system_instruction"),
            history_messages=history_messages,
            user_message=user_message,
            estimated_total_tokens=int(data.get("estimated_total_tokens", 0)),
            truncated_turn_count=int(data.get("truncated_turn_count", 0)),
            metadata=dict(data.get("metadata", {})),
        )
