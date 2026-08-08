"""ResourceManager and AdaptiveBudgetStrategy for resource tracking, budget limits, and strategy scaling."""

from __future__ import annotations

from dataclasses import dataclass


class ResourceQuotaExceededError(RuntimeError):
    """Exception raised when runtime resource budget ceiling is exceeded."""

    pass


@dataclass(frozen=True)
class ResourceBudget:
    """Configurable system resource budget limits.

    Attributes:
        cpu_limit_percent: Maximum allowed CPU percentage limit.
        ram_limit_mb: Maximum allowed RAM limit in MB.
        token_budget_units: Maximum allowed token budget.
        max_concurrent_workers: Maximum allowed parallel worker concurrency.
        max_api_cost: Maximum allowed API cost.
    """

    cpu_limit_percent: float = 80.0
    ram_limit_mb: float = 2048.0
    token_budget_units: int = 32000
    max_concurrent_workers: int = 8
    max_api_cost: float = 5.0


@dataclass(frozen=True)
class AdaptiveBudgetAdaptation:
    """Adaptive resource adjustment recommendations based on remaining budget."""

    target_concurrency: int
    target_max_context_units: int
    recommend_cheap_model: bool


class ResourceManager:
    """Tracks active runtime resource consumption and enforces resource budget limits."""

    def __init__(self, budget: ResourceBudget | None = None) -> None:
        self.budget = budget or ResourceBudget()
        self._current_tokens_used = 0
        self._current_cost_usd = 0.0
        self._active_workers = 0

    def acquire_worker(self) -> None:
        """Acquire a worker slot, verifying concurrency ceiling."""
        if self._active_workers >= self.budget.max_concurrent_workers:
            raise ResourceQuotaExceededError(
                f"Worker limit exceeded: {self._active_workers} >= {self.budget.max_concurrent_workers}"
            )
        self._active_workers += 1

    def release_worker(self) -> None:
        """Release an active worker slot."""
        self._active_workers = max(0, self._active_workers - 1)

    def consume_tokens_and_cost(self, tokens: int, cost_usd: float) -> None:
        """Record token consumption and cost, enforcing budget limits."""
        if self._current_tokens_used + tokens > self.budget.token_budget_units:
            raise ResourceQuotaExceededError(
                f"Token budget exceeded: {self._current_tokens_used + tokens} > {self.budget.token_budget_units}"
            )

        if self._current_cost_usd + cost_usd > self.budget.max_api_cost:
            raise ResourceQuotaExceededError(
                f"API cost ceiling exceeded: {self._current_cost_usd + cost_usd:.2f} > {self.budget.max_api_cost:.2f}"
            )

        self._current_tokens_used += tokens
        self._current_cost_usd += cost_usd

    def compute_adaptive_adaptation(self) -> AdaptiveBudgetAdaptation:
        """Calculate adaptive resource adaptation based on remaining token and cost ratio."""
        token_ratio = self._current_tokens_used / max(1, self.budget.token_budget_units)
        cost_ratio = self._current_cost_usd / max(0.01, self.budget.max_api_cost)
        max_ratio = max(token_ratio, cost_ratio)

        if max_ratio > 0.8:
            return AdaptiveBudgetAdaptation(
                target_concurrency=1,
                target_max_context_units=8000,
                recommend_cheap_model=True,
            )
        elif max_ratio > 0.5:
            return AdaptiveBudgetAdaptation(
                target_concurrency=max(1, self.budget.max_concurrent_workers // 2),
                target_max_context_units=16000,
                recommend_cheap_model=False,
            )
        else:
            return AdaptiveBudgetAdaptation(
                target_concurrency=self.budget.max_concurrent_workers,
                target_max_context_units=self.budget.token_budget_units,
                recommend_cheap_model=False,
            )
