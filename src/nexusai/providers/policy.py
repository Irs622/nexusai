"""Provider Policy Layer for decoupling provider evaluation and selection logic."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

from nexusai.core.annotations import stable
from nexusai.logging.logger import logger
from nexusai.providers.base import BaseProvider
from nexusai.providers.models import Capability, CapabilityLevel, ChatRequest


@stable
@dataclass(frozen=True)
class PolicyResult:
    """Evaluation result returned by a ProviderPolicy."""

    allow: bool = True
    score: float = 1.0
    reason: str = ""


@stable
class BaseProviderPolicy(ABC):
    """Abstract interface for provider evaluation and routing policies."""

    @abstractmethod
    async def evaluate(
        self,
        provider: BaseProvider,
        request: ChatRequest | None = None,
    ) -> PolicyResult:
        """Evaluate a single provider candidate against policy rules.

        Args:
            provider: Target BaseProvider instance.
            request: Optional ChatRequest.

        Returns:
            PolicyResult snapshot.
        """
        ...

    async def filter(
        self,
        candidates: Sequence[BaseProvider],
        request: ChatRequest | None = None,
    ) -> list[BaseProvider]:
        """Filter and rank candidate providers based on policy score.

        Args:
            candidates: Sequence of candidate providers.
            request: Optional ChatRequest.

        Returns:
            Ranked list of candidate providers whose policy score > 0 and allow is True.
        """
        scored: list[tuple[float, BaseProvider]] = []
        for provider in candidates:
            res = await self.evaluate(provider, request=request)
            if res.allow and res.score > 0:
                scored.append((res.score, provider))

        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored]


@stable
class CapabilityPolicy(BaseProviderPolicy):
    """Policy evaluating candidates by required capability and minimum support level."""

    def __init__(
        self,
        required_capabilities: set[Capability],
        min_level: CapabilityLevel = CapabilityLevel.BASIC,
    ) -> None:
        self.required_capabilities = required_capabilities
        self.min_level = min_level

    async def evaluate(
        self,
        provider: BaseProvider,
        request: ChatRequest | None = None,
    ) -> PolicyResult:
        if all(
            provider.metadata.capabilities.supports(cap, self.min_level)
            for cap in self.required_capabilities
        ):
            return PolicyResult(allow=True, score=1.0, reason="Supports required capabilities")
        return PolicyResult(allow=False, score=0.0, reason="Missing required capabilities")


@stable
class AvailabilityPolicy(BaseProviderPolicy):
    """Policy evaluating candidates by health reachability."""

    async def evaluate(
        self,
        provider: BaseProvider,
        request: ChatRequest | None = None,
    ) -> PolicyResult:
        try:
            health = await provider.health_check()
            if health.healthy:
                score = 1.0 / (1.0 + (health.latency_ms / 1000.0))
                return PolicyResult(
                    allow=True, score=score, reason=f"Healthy (latency={health.latency_ms:.1f}ms)"
                )
            return PolicyResult(allow=False, score=0.0, reason=f"Unhealthy: {health.error}")
        except Exception as err:
            logger.warning("AvailabilityPolicy evaluation error for '{}': {}", provider.id, err)
            return PolicyResult(allow=False, score=0.0, reason=str(err))


@stable
class CompositePolicy(BaseProviderPolicy):
    """Policy combining multiple policies sequentially with weighted score calculation."""

    def __init__(self, policies: list[BaseProviderPolicy]) -> None:
        self.policies = policies

    async def evaluate(
        self,
        provider: BaseProvider,
        request: ChatRequest | None = None,
    ) -> PolicyResult:
        total_score = 0.0
        reasons: list[str] = []

        for policy in self.policies:
            res = await policy.evaluate(provider, request=request)
            if not res.allow:
                return PolicyResult(
                    allow=False,
                    score=0.0,
                    reason=f"Rejected by {policy.__class__.__name__}: {res.reason}",
                )
            total_score += res.score
            if res.reason:
                reasons.append(res.reason)

        avg_score = total_score / max(len(self.policies), 1)
        return PolicyResult(allow=True, score=avg_score, reason="; ".join(reasons))
