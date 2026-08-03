"""Dynamic Provider Router based on Health Score, Cost, and Capability."""
from typing import List, Dict, Any, Optional
from nexusai.models.base import BaseModelProvider
from nexusai.models.circuit_breaker import CircuitBreaker

class ProviderRouter:
    """Routes requests to the optimal LLM provider based on real-time metrics and capabilities."""

    def __init__(self, providers: Dict[str, BaseModelProvider]) -> None:
        self.providers = providers
        self.circuit_breakers: Dict[str, CircuitBreaker] = {
            pid: CircuitBreaker(provider_id=pid) for pid in providers
        }

    def select_best_provider(self, task_type: str = "general") -> tuple[str, BaseModelProvider]:
        """Select the highest-performing available provider."""
        best_pid: Optional[str] = None
        best_score: float = -1.0

        for pid, cb in self.circuit_breakers.items():
            if cb.can_execute():
                score = cb.calculate_health_score()
                if score > best_score:
                    best_score = score
                    best_pid = pid

        if best_pid and best_pid in self.providers:
            return best_pid, self.providers[best_pid]

        # Fallback to first provider entry
        first_pid = next(iter(self.providers))
        return first_pid, self.providers[first_pid]
