"""Deprecated alias of :mod:`nexusai.providers.circuit_breaker`.

``CircuitBreaker`` and ``CircuitState`` now live in ``nexusai.providers.circuit_breaker``
(single canonical implementation, ADR 0037). Importing them from here still works but
emits a ``DeprecationWarning``; this alias will be removed in a future minor release.
``from nexusai.runtime import CircuitBreaker`` keeps working without a warning.
"""

from __future__ import annotations

import warnings
from typing import Any

from nexusai.providers import circuit_breaker as _canonical

_DEPRECATED_NAMES = {"CircuitBreaker", "CircuitState"}

__all__ = sorted(_DEPRECATED_NAMES)


def __getattr__(name: str) -> Any:
    if name in _DEPRECATED_NAMES:
        warnings.warn(
            f"nexusai.runtime.circuit_breaker.{name} is deprecated; "
            f"import it from nexusai.providers.circuit_breaker instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(_canonical, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
