"""
Centralized exception hierarchy for NexusAI.
"""

from __future__ import annotations


class NexusAIError(Exception):
    """Base exception class for all NexusAI errors."""

    def __init__(self, message: str, details: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(NexusAIError):
    """Raised when there is an issue loading or parsing system configuration."""

    pass


class SecurityError(NexusAIError):
    """Raised when a security policy violation or unauthorized command execution occurs."""

    pass


class CommandExecutionError(NexusAIError):
    """Raised when a CQRS command execution fails."""

    pass


class QueryExecutionError(NexusAIError):
    """Raised when a CQRS query execution fails."""

    pass


class ToolExecutionError(NexusAIError):
    """Raised when an automation tool encounters a runtime failure."""

    pass


class PluginError(NexusAIError):
    """Raised during plugin lifecycle operations (install, enable, disable, reload)."""

    pass


class ModelProviderError(NexusAIError):
    """Raised when an LLM provider encounters an API error or timeout."""

    pass
