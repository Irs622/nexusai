"""Exceptions and fine-grained Error Taxonomy for the NexusAI Provider SDK foundation."""

from __future__ import annotations

from nexusai.core.annotations import stable
from nexusai.core.errors import NexusAIError


@stable
class ProviderSDKError(NexusAIError):
    """Base exception class for all Provider SDK errors."""

    pass


@stable
class ProviderNotFoundError(ProviderSDKError):
    """Raised when a requested provider is not found in the registry."""

    pass


@stable
class ProviderRegistrationError(ProviderSDKError):
    """Raised when a provider registration operation fails."""

    pass


@stable
class ProviderConfigurationError(ProviderSDKError):
    """Raised when a provider is misconfigured or default provider is missing."""

    pass


@stable
class ProviderAuthenticationError(ProviderSDKError):
    """Raised when provider authentication fails (e.g. invalid API key)."""

    pass


@stable
class ProviderRateLimitError(ProviderSDKError):
    """Raised when a provider API rate limit is exceeded."""

    pass


@stable
class ProviderTimeoutError(ProviderSDKError):
    """Raised when a provider API request times out."""

    pass


@stable
class ProviderNetworkError(ProviderSDKError):
    """Raised when a network connectivity failure occurs."""

    pass


@stable
class ProviderCircuitOpenError(ProviderSDKError):
    """Raised when a request is blocked because the provider's CircuitBreaker is OPEN."""

    pass
