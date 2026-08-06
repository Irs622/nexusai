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


class WorkflowError(NexusAIError):
    """Raised when a workflow graph encounters an execution or routing failure."""

    pass


# --- Kernel Engine Exceptions ---


class KernelError(NexusAIError):
    """Base class for all OS Kernel Orchestration Engine errors."""

    pass


class ServiceRegistrationError(KernelError):
    """Raised when service registration fails (e.g. duplicate ID or invalid metadata)."""

    pass


class DependencyCycleError(KernelError):
    """Raised when circular dependencies are detected in the runtime service graph."""

    pass


class MissingDependencyError(KernelError):
    """Raised when a required service dependency cannot be resolved."""

    pass


class LifecycleStateError(KernelError):
    """Raised when an invalid service lifecycle transition is attempted."""

    pass


class KernelBootstrapError(KernelError):
    """Raised when the OS Kernel fails during multi-stage bootstrap sequence."""

    pass


class GraphFrozenError(KernelError):
    """Raised when attempting to modify a service dependency graph that has been frozen."""

    pass


