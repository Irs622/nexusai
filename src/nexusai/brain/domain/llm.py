"""Vendor-neutral domain models, message taxonomy, response objects, and normalized error hierarchy for LLM Providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Mapping

from nexusai.brain.domain.observability import sanitize_attributes


class LLMRole(str, Enum):
    """Normalized role taxonomy for LLM conversation messages."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class FinishReason(str, Enum):
    """Normalized completion termination reason."""

    STOP = "stop"
    LENGTH = "length"
    TOOL_CALL = "tool_call"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"


# ------------------------------------------------------------------
# Normalized Exception Hierarchy
# ------------------------------------------------------------------

class LLMError(Exception):
    """Base class for all vendor-neutral LLM provider errors."""

    pass


class LLMAuthenticationError(LLMError):
    """Raised when provider authentication or API key validation fails."""

    pass


class LLMRateLimitError(LLMError):
    """Raised when provider rate limits or quotas are exceeded."""

    pass


class LLMTimeoutError(LLMError):
    """Raised when an LLM model request exceeds its configured timeout ceiling."""

    pass


class LLMProviderUnavailableError(LLMError):
    """Raised when the requested provider or endpoint is unreachable or unregistered."""

    pass


LLMUnavailableError = LLMProviderUnavailableError



class LLMInvalidRequestError(LLMError):
    """Raised when the request parameters or message payload are invalid."""

    pass


class LLMResponseError(LLMError):
    """Raised when the provider response format is malformed or unparseable."""

    pass


class LLMResponseFormatError(LLMResponseError):
    """Raised when model-generated structured JSON output fails schema or domain validation."""

    pass



# ------------------------------------------------------------------
# Domain Models
# ------------------------------------------------------------------

@dataclass(frozen=True)
class LLMMessage:
    """Immutable domain representation of an LLM request message."""

    role: LLMRole
    content: str


@dataclass(frozen=True)
class LLMRequest:
    """Immutable vendor-neutral LLM request payload."""

    model: str
    messages: tuple[LLMMessage, ...]
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout_seconds: float = 60.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate request invariants and sanitize secret metadata."""
        if not self.model.strip():
            raise ValueError("model cannot be empty")
        if not self.messages:
            raise ValueError("messages tuple cannot be empty")
        if self.timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds must be greater than 0")

        # Secret redaction invariant (P3-3-INV-01 & P3-3-INV-02)
        sanitized = sanitize_attributes(self.metadata)
        object.__setattr__(self, "metadata", sanitized)


@dataclass(frozen=True)
class LLMUsage:
    """Immutable token usage metrics."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class LLMResponse:
    """Immutable vendor-neutral LLM completion response."""

    provider: str
    model: str
    content: str
    finish_reason: FinishReason
    usage: LLMUsage | None = None
    request_id: str | None = None
    latency_ms: float = 0.0


@dataclass(frozen=True)
class LLMProviderConfig:
    """Configuration contract for resolving provider infrastructure endpoints and timeouts."""

    provider_name: str
    default_model: str
    api_key_env: str | None = None
    endpoint: str | None = None
    default_timeout_seconds: float = 60.0
    max_tokens: int = 4096

    def __post_init__(self) -> None:
        if not self.provider_name.strip():
            raise ValueError("provider_name cannot be empty")
        if not self.default_model.strip():
            raise ValueError("default_model cannot be empty")
