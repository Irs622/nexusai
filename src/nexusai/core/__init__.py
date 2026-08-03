"""
Core Package containing config, container, and exception abstractions.
"""

from nexusai.core.errors import (
    NexusAIError,
    ConfigurationError,
    SecurityError,
    CommandExecutionError,
    QueryExecutionError,
    ToolExecutionError,
    PluginError,
    ModelProviderError,
)
from nexusai.core.config import SystemConfig, AppSettings, LoggingSettings, ModelSettings, SecuritySettings, PathSettings
from nexusai.core.container import DependencyContainer

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
    "CommandExecutionError",
    "QueryExecutionError",
    "ToolExecutionError",
    "PluginError",
    "ModelProviderError",
]
