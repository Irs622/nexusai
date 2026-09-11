"""
Core Package containing config, container, and exception abstractions.
"""

from nexusai.core.config import (
    AppSettings,
    LoggingSettings,
    ModelSettings,
    PathSettings,
    SecuritySettings,
    SystemConfig,
)
from nexusai.core.container import DependencyContainer
from nexusai.core.errors import (
    AuthenticationError,
    AuthorizationError,
    CommandExecutionError,
    ConfigurationError,
    ModelProviderError,
    NexusAIError,
    PluginError,
    QueryExecutionError,
    RateLimitExceededError,
    SecurityError,
    ToolExecutionError,
)

__all__ = [
    "SystemConfig",
    "AppSettings",
    "LoggingSettings",
    "ModelSettings",
    "SecuritySettings",
    "PathSettings",
    "DependencyContainer",
    "NexusAIError",
    "ConfigurationError",
    "SecurityError",
    "AuthenticationError",
    "AuthorizationError",
    "RateLimitExceededError",
    "CommandExecutionError",
    "QueryExecutionError",
    "ToolExecutionError",
    "PluginError",
    "ModelProviderError",
]
