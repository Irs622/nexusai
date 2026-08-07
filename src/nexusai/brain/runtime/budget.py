"""
ExecutionBudget (immutable limits) and ExecutionUsage (mutable tracking) runtime models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexusai.core.errors import BrainContextAssemblyError


@dataclass(frozen=True)
class ExecutionBudget:
    """Immutable resource ceiling configuration for turn execution.

    Attributes:
        max_input_tokens: Maximum allowed input tokens.
        max_output_tokens: Maximum allowed generated output tokens.
        max_time_ms: Hard wall-clock timeout in milliseconds.
        max_cost_usd: Optional monetary cost ceiling in USD.
        max_memory_bytes: Optional heap memory ceiling in bytes.
    """

    max_input_tokens: int = 128000
    max_output_tokens: int = 4096
    max_time_ms: float = 60000.0
    max_cost_usd: float | None = None
    max_memory_bytes: int | None = None

    def __post_init__(self) -> None:
        """Enforce ExecutionBudget invariants."""
        if self.max_input_tokens <= 0:
            raise BrainContextAssemblyError(
                f"ExecutionBudget invariant violated: max_input_tokens ({self.max_input_tokens}) must be positive."
            )
        if self.max_output_tokens <= 0:
            raise BrainContextAssemblyError(
                f"ExecutionBudget invariant violated: max_output_tokens ({self.max_output_tokens}) must be positive."
            )
        if self.max_time_ms <= 0.0:
            raise BrainContextAssemblyError(
                f"ExecutionBudget invariant violated: max_time_ms ({self.max_time_ms}) must be positive."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize ExecutionBudget to dictionary format."""
        return {
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_time_ms": self.max_time_ms,
            "max_cost_usd": self.max_cost_usd,
            "max_memory_bytes": self.max_memory_bytes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionBudget:
        """Deserialize ExecutionBudget from dictionary format."""
        return cls(
            max_input_tokens=int(data.get("max_input_tokens", 128000)),
            max_output_tokens=int(data.get("max_output_tokens", 4096)),
            max_time_ms=float(data.get("max_time_ms", 60000.0)),
            max_cost_usd=float(data["max_cost_usd"]) if data.get("max_cost_usd") is not None else None,
            max_memory_bytes=int(data["max_memory_bytes"]) if data.get("max_memory_bytes") is not None else None,
        )


@dataclass
class ExecutionUsage:
    """Mutable runtime metrics counter tracking active resource usage during turn execution.

    Attributes:
        used_input_tokens: Total input tokens consumed.
        used_output_tokens: Total output tokens generated.
        used_time_ms: Elapsed execution time in milliseconds.
        used_cost_usd: Accumulated monetary cost in USD.
        used_memory_bytes: Estimated memory allocated in bytes.
    """

    used_input_tokens: int = 0
    used_output_tokens: int = 0
    used_time_ms: float = 0.0
    used_cost_usd: float = 0.0
    used_memory_bytes: int = 0

    def add_input_tokens(self, count: int) -> None:
        """Accumulate input tokens with invariant validation."""
        if count < 0:
            raise ValueError(f"ExecutionUsage invariant violated: count ({count}) cannot be negative.")
        self.used_input_tokens += count

    def add_output_tokens(self, count: int) -> None:
        """Accumulate output tokens with invariant validation."""
        if count < 0:
            raise ValueError(f"ExecutionUsage invariant violated: count ({count}) cannot be negative.")
        self.used_output_tokens += count

    @property
    def total_tokens(self) -> int:
        """Calculate total consumed tokens."""
        return self.used_input_tokens + self.used_output_tokens

    def to_dict(self) -> dict[str, Any]:
        """Serialize ExecutionUsage to dictionary format."""
        return {
            "used_input_tokens": self.used_input_tokens,
            "used_output_tokens": self.used_output_tokens,
            "used_time_ms": self.used_time_ms,
            "used_cost_usd": self.used_cost_usd,
            "used_memory_bytes": self.used_memory_bytes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionUsage:
        """Deserialize ExecutionUsage from dictionary format."""
        return cls(
            used_input_tokens=int(data.get("used_input_tokens", 0)),
            used_output_tokens=int(data.get("used_output_tokens", 0)),
            used_time_ms=float(data.get("used_time_ms", 0.0)),
            used_cost_usd=float(data.get("used_cost_usd", 0.0)),
            used_memory_bytes=int(data.get("used_memory_bytes", 0)),
        )
