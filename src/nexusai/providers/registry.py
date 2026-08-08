"""Provider Registry for registering and retrieving Provider SDK instances."""

from __future__ import annotations

from nexusai.core.annotations import stable
from nexusai.logging.logger import logger
from nexusai.providers.base import BaseProvider
from nexusai.providers.exceptions import (
    ProviderConfigurationError,
    ProviderNotFoundError,
    ProviderRegistrationError,
)
from nexusai.providers.models import ProviderMetadata


@stable
class ProviderRegistry:
    """Instance-based registry for storing and retrieving provider adapters."""

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}
        self._default_provider_id: str | None = None

    def register(self, provider: BaseProvider, is_default: bool = False) -> None:
        """Register a provider adapter instance.

        Args:
            provider: The BaseProvider instance to register.
            is_default: If True, sets this provider as the default.

        Raises:
            ProviderRegistrationError: If provider.id is already registered.
        """
        provider_id = provider.id
        if provider_id in self._providers:
            logger.error("Provider registration failed: '{}' is already registered", provider_id)
            raise ProviderRegistrationError(f"Provider '{provider_id}' is already registered.")

        self._providers[provider_id] = provider
        logger.info("Registered provider '{}'", provider_id)

        if is_default or self._default_provider_id is None:
            self._default_provider_id = provider_id
            logger.info("Default provider set to '{}'", provider_id)

    def unregister(self, provider_id: str) -> None:
        """Unregister a provider by identifier.

        Args:
            provider_id: Identifier string of the provider to remove.

        Raises:
            ProviderNotFoundError: If provider_id is not registered.
        """
        if provider_id not in self._providers:
            logger.error("Provider unregistration failed: '{}' not found", provider_id)
            raise ProviderNotFoundError(f"Provider '{provider_id}' is not registered.")

        del self._providers[provider_id]
        logger.info("Unregistered provider '{}'", provider_id)

        if self._default_provider_id == provider_id:
            self._default_provider_id = next(iter(self._providers.keys()), None)
            if self._default_provider_id:
                logger.info("Fallback default provider set to '{}'", self._default_provider_id)

    def get(self, provider_id: str) -> BaseProvider:
        """Retrieve a registered provider by identifier.

        Args:
            provider_id: Identifier string of target provider.

        Returns:
            The BaseProvider instance.

        Raises:
            ProviderNotFoundError: If provider_id is not registered.
        """
        pid = provider_id.id if hasattr(provider_id, "id") else str(provider_id)
        if pid not in self._providers:
            logger.error("Provider lookup failed: '{}' not found", pid)
            raise ProviderNotFoundError(f"Provider '{pid}' is not registered.")
        return self._providers[pid]

    def list_providers(self) -> list[ProviderMetadata]:
        """List metadata of all registered providers.

        Returns:
            List of ProviderMetadata for all registered providers.
        """
        return [p.metadata for p in self._providers.values()]

    def list_provider_ids(self) -> list[str]:
        """List all registered provider identifiers.

        Returns:
            List of provider ID strings.
        """
        return list(self._providers.keys())

    def get_default(self) -> BaseProvider:
        """Retrieve the default provider.

        Returns:
            The default BaseProvider instance.

        Raises:
            ProviderConfigurationError: If no default provider is set or registered.
        """
        if self._default_provider_id is None or self._default_provider_id not in self._providers:
            logger.error("No default provider configured")
            raise ProviderConfigurationError("No default provider has been set.")
        return self._providers[self._default_provider_id]

    def set_default(self, provider_id: str | BaseProvider) -> None:
        """Set default provider by identifier or provider instance."""
        pid = provider_id.id if hasattr(provider_id, "id") else str(provider_id)
        if pid not in self._providers:
            raise ProviderNotFoundError(f"Cannot set default: Provider '{pid}' is not registered.")
        self._default_provider_id = pid
        logger.info("Default provider explicitly set to '{}'", pid)
