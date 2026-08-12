"""Domain models, status enums, trust levels, and metadata contracts for Tool Registry & Capability Mapping."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
import time
from typing import Any, Mapping

from nexusai.brain.domain.governance import ResourceRequest, ToolCapability
from nexusai.brain.domain.observability import sanitize_attributes


class ToolStatus(str, Enum):
    """Lifecycle status taxonomy for registered tools."""

    REGISTERED = "REGISTERED"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    DEPRECATED = "DEPRECATED"
    REVOKED = "REVOKED"


class ToolTrustLevel(str, Enum):
    """Trust boundary classification for tools."""

    BUILTIN = "BUILTIN"
    VERIFIED = "VERIFIED"
    THIRD_PARTY = "THIRD_PARTY"
    UNTRUSTED = "UNTRUSTED"


class ToolIdempotency(str, Enum):
    """Execution idempotency safety classification for tool operations."""

    IDEMPOTENT = "IDEMPOTENT"
    NON_IDEMPOTENT = "NON_IDEMPOTENT"
    UNKNOWN = "UNKNOWN"



class ToolAlreadyRegisteredError(ValueError):
    """Raised when attempting to register a tool_id that is already registered."""

    pass


class ToolUnavailableError(RuntimeError):
    """Raised when attempting to resolve or execute a DISABLED or REVOKED tool."""

    pass


class ToolVersionMismatchError(ValueError):
    """Raised when an requested tool version does not match registered version."""

    pass


class CapabilityEscalationError(PermissionError):
    """Raised when a requested execution attempts to dynamically add undeclared capabilities."""

    pass


class TrustPolicyError(PermissionError):
    """Raised when an UNTRUSTED tool is rejected by registry trust policy."""

    pass


SEMVER_REGEX = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


@dataclass(frozen=True)
class ToolMetadata:
    """Immutable domain metadata representation for a registered tool."""

    tool_id: str
    name: str
    version: str
    description: str
    capabilities: frozenset[ToolCapability]
    status: ToolStatus = ToolStatus.ENABLED
    trust_level: ToolTrustLevel = ToolTrustLevel.BUILTIN
    owner: str = "core-system"
    source: str = "nexusai.tools"
    max_execution_seconds: float | None = None
    resource_request: ResourceRequest | None = None
    idempotent: bool = False
    registered_at: float = field(default_factory=time.time)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate metadata domain invariants and sanitize secret attributes."""
        if not self.tool_id.strip():
            raise ValueError("tool_id cannot be empty")
        if not self.name.strip():
            raise ValueError("name cannot be empty")
        if not self.owner.strip():
            raise ValueError("owner cannot be empty")
        if not self.source.strip():
            raise ValueError("source cannot be empty")
        if not SEMVER_REGEX.match(self.version):
            raise ValueError(f"Invalid semantic version format: '{self.version}' (must match X.Y.Z)")
        if self.max_execution_seconds is not None and self.max_execution_seconds <= 0:
            raise ValueError("max_execution_seconds must be greater than 0")

        # Secret redaction invariant
        sanitized = sanitize_attributes(self.metadata)
        object.__setattr__(self, "metadata", sanitized)


def validate_declared_capabilities(
    metadata: ToolMetadata,
    requested_capabilities: frozenset[ToolCapability],
) -> None:
    """Ensure requested capabilities are a strict subset of declared tool capabilities."""
    if not requested_capabilities.issubset(metadata.capabilities):
        undeclared = requested_capabilities - metadata.capabilities
        raise CapabilityEscalationError(
            f"Capability escalation detected for tool '{metadata.tool_id}': "
            f"requested undeclared capabilities {[c.value for c in undeclared]}"
        )
