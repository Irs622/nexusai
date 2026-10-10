"""Deprecated alias of :mod:`nexusai.plugins.runtime.loader`.

``PluginLoader`` and ``PluginLoadError`` now live in ``nexusai.plugins.runtime.loader``
(single canonical implementation, AUDIT-21). Importing them from here still works but
emits a ``DeprecationWarning``; this alias will be removed in a future minor release.
"""

from __future__ import annotations

import warnings
from typing import Any

from nexusai.plugins.runtime import loader as _canonical

_DEPRECATED_NAMES = {"PluginLoader", "PluginLoadError"}

__all__ = sorted(_DEPRECATED_NAMES)


def __getattr__(name: str) -> Any:
    if name in _DEPRECATED_NAMES:
        warnings.warn(
            f"nexusai.tools.plugin_loader.{name} is deprecated; "
            f"import it from nexusai.plugins.runtime.loader instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(_canonical, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
