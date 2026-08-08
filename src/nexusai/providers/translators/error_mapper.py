"""Canonical Error Mapper translating vendor HTTP status codes and payloads into SDK exceptions."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from nexusai.core.annotations import stable
from nexusai.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderNetworkError,
    ProviderNotFoundError,
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
        headers: dict[str, str] | None = None,
    ) -> ProviderSDKError:
        """Map HTTP status codes and error payloads into fine-grained SDK exception hierarchy.

        Args:
            status_code: HTTP response status code.
            raw_body: Raw error body (dict or string).
            provider_id: Provider identifier.
            headers: Optional HTTP response headers dict.

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
        if status_code == 404 or "not found" in error_msg.lower():
            return ProviderNotFoundError(msg)
        if status_code == 429:
            retry_after: float | None = None
            if headers:
                hdr_val = next(
                    (v for k, v in headers.items() if k.lower() == "retry-after"),
                    None,
                )
                if hdr_val is not None:
                    try:
                        retry_after = float(hdr_val)
                    except ValueError:
                        try:
                            dt = parsedate_to_datetime(hdr_val)
                            now = datetime.now(timezone.utc)
                            diff = (dt - now).total_seconds()
                            retry_after = max(0.0, diff)
                        except Exception:
                            retry_after = None
            return ProviderRateLimitError(msg, retry_after=retry_after)
        if status_code in (408, 504):
            return ProviderTimeoutError(msg)
        if status_code in (500, 502, 503):
            return ProviderNetworkError(msg)
        if status_code == 400:
            return ProviderConfigurationError(msg)

        return ProviderSDKError(msg)
