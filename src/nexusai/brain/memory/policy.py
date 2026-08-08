"""MemoryPolicy for retention, privacy, and token budget allocation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryPolicy:
    """Configurable memory policy governing retention, privacy filters, and token budgets.

    Attributes:
        max_context_units: Context budget ceiling in ContextUnits.
        enable_privacy_filter: Toggle privacy redaction filter.
        retention_half_life_sec: Half-life decay factor for recency scoring.
        max_retained_items: Maximum memory items to assemble in final context.
    """

    max_context_units: int = 32000
    enable_privacy_filter: bool = True
    retention_half_life_sec: float = 3600.0
    max_retained_items: int = 10
