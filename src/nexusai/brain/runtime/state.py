"""
SessionState, ModelCapabilities, ExecutionMode, and ExecutionFeatures runtime models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from nexusai.core.errors import BrainContextAssemblyError


class ExecutionMode(str, Enum):
    """Macro execution mode enumeration."""

    CHAT = "chat"
    AGENT = "agent"
    BATCH = "batch"


@dataclass(frozen=True)
class ExecutionFeatures:
    """Decoupled feature flags for turn execution.

    Attributes:
        streaming: Enables delta streaming output.
        audio: Enables audio multimodal processing.
        tools: Enables tool invocation support.
        reasoning: Enables deep reasoning/thinking capabilities.
    """

    streaming: bool = True
    audio: bool = False
    tools: bool = False
    reasoning: bool = False


@dataclass(frozen=True)
class ModelCapabilities:
    """Model context window and capability constraints.

    Attributes:
        max_input_tokens: Upper bound on input context tokens.
        max_output_tokens: Upper bound on generated output tokens.
        reserved_tokens: Safety margin reserved for system instructions and overhead.
    """

    max_input_tokens: int
    max_output_tokens: int
    reserved_tokens: int = 512

    def __post_init__(self) -> None:
        """Enforce domain invariants for ModelCapabilities."""
        if self.max_input_tokens <= 0:
            raise BrainContextAssemblyError(
                f"ModelCapabilities invariant violated: max_input_tokens ({self.max_input_tokens}) must be positive."
            )
        if self.max_output_tokens <= 0:
            raise BrainContextAssemblyError(
                f"ModelCapabilities invariant violated: max_output_tokens ({self.max_output_tokens}) must be positive."
            )
        if self.reserved_tokens < 0:
            raise BrainContextAssemblyError(
                f"ModelCapabilities invariant violated: reserved_tokens ({self.reserved_tokens}) cannot be negative."
            )


@dataclass
class SessionState:
    """Mutable runtime execution configuration associated with a BrainSession.

    Attributes:
        provider_id: ID of the active model provider.
        active_model: Specific target model identifier.
        generation_config: Parameters (temperature, top_p, etc.).
        model_capabilities: Token limits and capabilities.
        execution_mode: Operational mode (CHAT, AGENT, BATCH).
        execution_features: Active feature flags.
        default_system_prompt: Default system instruction override.
        memory_profile: Memory retrieval configuration.
        turn_count: Number of turns executed within this session.
        updated_at: Timestamp of last state mutation.
    """

    provider_id: str
    active_model: str
    generation_config: dict[str, Any] = field(default_factory=dict)
    model_capabilities: ModelCapabilities = field(
        default_factory=lambda: ModelCapabilities(max_input_tokens=128000, max_output_tokens=4096)
    )
    execution_mode: ExecutionMode = ExecutionMode.CHAT
    execution_features: ExecutionFeatures = field(default_factory=ExecutionFeatures)
    default_system_prompt: str | None = None
    memory_profile: dict[str, Any] = field(default_factory=dict)
    turn_count: int = 0
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
