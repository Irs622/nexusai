"""
Custom exception hierarchy for NexusAI Plugin Engine.
"""

from __future__ import annotations

from nexusai.core.errors import PluginError


class PluginManifestError(PluginError):
    """Raised when a plugin manifest schema or parsing operation fails."""

    pass


class PluginValidationError(PluginError):
    """Raised when plugin metadata, structure, or permissions fail validation."""

    pass


class PluginAPIVersionError(PluginValidationError):
    """Raised when plugin API version is incompatible with Kernel API version."""

    pass


class PluginDependencyError(PluginValidationError):
    """Raised when plugin dependencies are missing, invalid, or cyclic."""

    pass


class PluginResolutionError(PluginError):
    """Raised when plugin capability or ID resolution fails."""

    pass


class PluginLoadError(PluginError):
    """Raised when dynamic module importing or plugin instantiation fails."""

    pass


class PluginLifecycleError(PluginError):
    """Raised when an invalid plugin lifecycle state transition occurs."""

    pass


class PluginPermissionError(PluginError):
    """Raised when a plugin attempts an unauthorized system or resource access."""

    pass


class PluginSandboxError(PluginError):
    """Raised when an error occurs inside the plugin execution sandbox."""

    pass


class PluginSignatureError(PluginError):
    """Raised when plugin manifest signature verification fails."""

    pass
