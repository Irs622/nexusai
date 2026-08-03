"""Canonical Error Mapper translating vendor HTTP status codes and payloads into SDK exceptions."""

from __future__ import annotations

from typing import Any

from nexusai.core.annotations import stable
from nexusai.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderSDKError,
    ProviderTimeoutError,
)


@stable
class CanonicalErrorMapper:
    """Error mapper ensuring raw vendor exceptions are never leaked to application layers."""

    @staticmethod
    def map_http_error(
        status_code: int,
        raw_body: Any,
        provider_id: str,
    ) -> ProviderSDKError:
        """Map HTTP status codes and error payloads into fine-grained SDK exception hierarchy.

        Args:
            status_code: HTTP response status code.
            raw_body: Raw error body (dict or string).
            provider_id: Provider identifier.

        Returns:
            Mapped ProviderSDKError instance.
        """
        error_msg = str(raw_body)
        if isinstance(raw_body, dict):
            err_dict = raw_body.get("error", raw_body)
            if isinstance(err_dict, dict):
                error_msg = err_dict.get("message", error_msg)

        msg = f"Provider '{provider_id}' error ({status_code}): {error_msg}"

        if status_code in (401, 403):
            return ProviderAuthenticationError(msg)
        if status_code == 429:
            return ProviderRateLimitError(msg)
        if status_code in (408, 504):
            return ProviderTimeoutError(msg)
        if status_code in (502, 503):
            return ProviderNetworkError(msg)
        if status_code == 400:
            return ProviderConfigurationError(msg)

        return ProviderSDKError(msg)
