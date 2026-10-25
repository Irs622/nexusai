"""Deprecated alias of :mod:`nexusai.providers.circuit_breaker`.

The canonical ``CircuitBreaker`` (ADR 0037) now carries the sliding-window metrics and
health score that used to live here. Importing ``CircuitBreaker`` or ``CircuitState`` from
this module still works but emits a ``DeprecationWarning``; it will be removed in a future
minor release.

The ``CircuitBreaker`` returned here is a thin subclass that keeps this module's former
defaults: ``provider_id`` is optional, a single success closes a HALF_OPEN circuit, and
``get_metrics()["state"]`` is upper-case. ``CircuitState`` is the canonical enum, whose
values are lower-case (``"open"``); compare against members, not raw strings.
"""

from __future__ import annotations

import warnings
from typing import Any

from nexusai.providers import circuit_breaker as _canonical
from nexusai.providers.clock import Clock


class _LegacyCircuitBreaker(_canonical.CircuitBreaker):
    """Canonical CircuitBreaker with the defaults of the former ``nexusai.models`` version."""

    def __init__(
        self,
        provider_id: str = "default_provider",
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        sliding_window_size: int = 50,
        success_threshold: int = 1,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(
            provider_id=provider_id,
            failure_threshold=failure_threshold,
            recovery_timeout_seconds=recovery_timeout_seconds,
            success_threshold=success_threshold,
            clock=clock,
            sliding_window_size=sliding_window_size,
        )

    def get_metrics(self) -> dict[str, Any]:
        metrics = super().get_metrics()
        metrics["state"] = str(metrics["state"]).upper()
        return metrics


_DEPRECATED = {"CircuitBreaker": _LegacyCircuitBreaker, "CircuitState": _canonical.CircuitState}

__all__ = sorted(_DEPRECATED)


def __getattr__(name: str) -> Any:
    if name in _DEPRECATED:
        warnings.warn(
            f"nexusai.models.circuit_breaker.{name} is deprecated; "
            f"import it from nexusai.providers.circuit_breaker instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _DEPRECATED[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
