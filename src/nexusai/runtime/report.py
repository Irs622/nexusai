"""Execution Report and Token Accounting model for runtime auditing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from nexusai.core.annotations import stable


@stable
@dataclass(frozen=True)
class ExecutionReport:
    """Comprehensive accounting report captured for every executed request in NexusAI."""

    request_id: str
    provider_id: str
    model: str
    token_in: int = 0
    token_out: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    retry_count: int = 0
    cache_hit: bool = False
    tool_count: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def summary(self) -> str:
        """Formatted summary string of execution metrics."""
        return (
            f"=== Execution Report [{self.request_id}] ===\n"
            f"Provider/Model: {self.provider_id} / {self.model}\n"
            f"Tokens (In/Out/Total): {self.token_in} / {self.token_out} / {self.total_tokens}\n"
            f"Cost: ${self.cost:.6f} | Latency: {self.latency_ms:.2f}ms | Retries: {self.retry_count}\n"
        )
