"""Policy-based Provider Router for candidate evaluation and provider selection."""

from __future__ import annotations

from nexusai.core.annotations import stable
from nexusai.logging.logger import logger
from nexusai.providers.base import BaseProvider
from nexusai.providers.exceptions import ProviderNotFoundError
from nexusai.providers.manager import ProviderManager
from nexusai.providers.models import Capability, CapabilityLevel, ChatRequest
from nexusai.providers.policy import BaseProviderPolicy, CapabilityPolicy


@stable
class ProviderRouter:
    """Policy-based selector and router for choosing optimal provider adapters."""

    def __init__(self, manager: ProviderManager) -> None:
        self._manager = manager

    @property
    def manager(self) -> ProviderManager:
        """Access the underlying ProviderManager."""
        return self._manager

    async def route(
        self,
        policy: BaseProviderPolicy | None = None,
        required_capabilities: set[Capability] | None = None,
        min_level: CapabilityLevel = CapabilityLevel.BASIC,
        request: ChatRequest | None = None,
    ) -> BaseProvider:
        """Route to the optimal BaseProvider instance using a ProviderPolicy.

        Args:
            policy: Explicit BaseProviderPolicy instance to evaluate. If None,
                defaults to a CapabilityPolicy using required_capabilities.
            required_capabilities: Set of required capabilities (if policy is None).
            min_level: Minimum required CapabilityLevel.
            request: Optional ChatRequest containing task specifications.

        Returns:
            The selected BaseProvider instance.

        Raises:
            ProviderNotFoundError: If no candidate provider satisfies the policy.
        """
        all_providers = [
            self._manager.registry.get(pid)
            for pid in self._manager.registry.list_provider_ids()
        ]

        active_policy = policy
        if active_policy is None:
            caps = required_capabilities or set()
            active_policy = CapabilityPolicy(required_capabilities=caps, min_level=min_level)

        # First filter by health reachability
        healthy_candidates = await self._manager.healthy_providers()
        candidates = await active_policy.filter(healthy_candidates, request=request)

        if candidates:
            selected = candidates[0]
            logger.info("ProviderRouter routed request to provider '{}'", selected.id)
            return selected

        # Fallback check for default provider
        try:
            default_p = self._manager.registry.get_default()
            health = await default_p.health_check()
            if health.healthy:
                logger.warning(
                    "No candidate provider passed policy evaluation; falling back to default provider '{}'",
                    default_p.id,
                )
                return default_p
        except Exception:
            pass

        logger.error("No suitable provider candidate found for policy evaluation")
        raise ProviderNotFoundError("No healthy provider found matching policy criteria.")

    async def select_provider(
        self,
        required_capabilities: set[Capability] | None = None,
        min_level: CapabilityLevel = CapabilityLevel.BASIC,
        tags: list[str] | None = None,
    ) -> BaseProvider:
        """Convenience method for capability-based provider selection."""
        return await self.route(
            required_capabilities=required_capabilities,
            min_level=min_level,
        )
