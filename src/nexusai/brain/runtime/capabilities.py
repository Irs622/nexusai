"""
Capability enumeration, ExecutionConstraints, and RequiredCapabilities models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Capability(str, Enum):
    """Canonical model capability enumeration."""

    VISION = "vision"
    JSON_MODE = "json_mode"
    FUNCTION_CALLING = "function_calling"
    LONG_CONTEXT = "long_context"
    REASONING = "reasoning"
    AUDIO = "audio"
    STREAMING = "streaming"


@dataclass(frozen=True)
class ExecutionConstraints:
    """Operational constraints for model route negotiation.

    Attributes:
        min_context_window: Minimum context window requirement in tokens.
        prefer_local: If True, prioritizes local on-device models (e.g. Ollama).
        max_cost_usd_per_1k: Optional cost ceiling per 1k tokens in USD.
    """

    min_context_window: int | None = None
    prefer_local: bool = False
    max_cost_usd_per_1k: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize ExecutionConstraints to dictionary format."""
        return {
            "min_context_window": self.min_context_window,
            "prefer_local": self.prefer_local,
            "max_cost_usd_per_1k": self.max_cost_usd_per_1k,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionConstraints:
        """Deserialize ExecutionConstraints from dictionary format."""
        return cls(
            min_context_window=data.get("min_context_window"),
            prefer_local=bool(data.get("prefer_local", False)),
            max_cost_usd_per_1k=data.get("max_cost_usd_per_1k"),
        )


@dataclass(frozen=True)
class RequiredCapabilities:
    """Requested model capability constraints submitted by clients or agents.

    Attributes:
        capabilities: Immutable tuple of required capability strings or Capability Enums.
        constraints: Operational constraints (cost, local preference, min context).
    """

    capabilities: tuple[str | Capability, ...] = field(default_factory=tuple)
    constraints: ExecutionConstraints = field(default_factory=ExecutionConstraints)

    def __post_init__(self) -> None:
        """Ensure capabilities list is converted to an immutable tuple."""
        if isinstance(self.capabilities, list):
            norm_caps = tuple(
                c.value if isinstance(c, Capability) else str(c) for c in self.capabilities
            )
            object.__setattr__(self, "capabilities", norm_caps)
        else:
            norm_caps = tuple(
                c.value if isinstance(c, Capability) else str(c) for c in self.capabilities
            )
            object.__setattr__(self, "capabilities", norm_caps)

    def has_capability(self, name: str | Capability) -> bool:
        """Check if a specific capability is required."""
        target_name = name.value if isinstance(name, Capability) else str(name)
        return target_name.lower() in (
            (cap.value if isinstance(cap, Capability) else str(cap)).lower()
            for cap in self.capabilities
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize RequiredCapabilities to dictionary format."""
        return {
            "capabilities": [
                c.value if isinstance(c, Capability) else str(c) for c in self.capabilities
            ],
            "constraints": self.constraints.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RequiredCapabilities:
        """Deserialize RequiredCapabilities from dictionary format."""
        caps = tuple(str(c) for c in data.get("capabilities", []))
        constraints_data = data.get("constraints", {})
        constraints = (
            ExecutionConstraints.from_dict(constraints_data)
            if isinstance(constraints_data, dict)
            else ExecutionConstraints()
        )

        return cls(
            capabilities=caps,
            constraints=constraints,
        )
