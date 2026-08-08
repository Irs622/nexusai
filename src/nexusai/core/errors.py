"""
Centralized exception hierarchy for NexusAI.
"""

from __future__ import annotations

from typing import Any


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


# --- Brain Runtime Exceptions ---


class BrainError(NexusAIError):
    """Base exception class for all Brain Runtime errors."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)


class BrainContextAssemblyError(BrainError):
    """Raised when assembling conversation context window fails."""

    pass


class BrainCapabilityNegotiationError(BrainError):
    """Raised when no model provider satisfies the requested capabilities."""

    pass


class BrainPromptRenderError(BrainError):
    """Raised when rendering prompt templates or bundles fails."""

    pass


class BrainProviderExecutionError(BrainError):
    """Raised when downstream model provider execution fails."""

    def __init__(
        self,
        message: str,
        provider_id: str | None = None,
        status_code: int | None = None,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged_details = details or {}
        if provider_id:
            merged_details["provider_id"] = provider_id
        if status_code is not None:
            merged_details["status_code"] = str(status_code)
        if request_id:
            merged_details["request_id"] = request_id
        super().__init__(message, details=merged_details)
        self.provider_id = provider_id
        self.status_code = status_code
        self.request_id = request_id


class BrainProviderUnavailableError(BrainProviderExecutionError):
    """Raised when downstream model provider is unreachable or returning 503/rate limits."""

    def __init__(
        self,
        message: str,
        provider_id: str | None = None,
        status_code: int | None = 503,
        retryable: bool = True,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged_details = details or {}
        merged_details["retryable"] = str(retryable)
        super().__init__(
            message=message,
            provider_id=provider_id,
            status_code=status_code,
            request_id=request_id,
            details=merged_details,
        )
        self.retryable = retryable


class BrainOutboxPersistenceError(BrainError):
    """Raised when transactional outbox persistence fails."""

    pass


class BrainTimeoutError(BrainError):
    """Raised when turn execution hits a timeout policy limit."""

    pass


class DuplicateObservationError(BrainError):
    """Raised when an observation with a duplicate ID is added to WorkingMemory."""

    pass


class GraphFrozenError(NexusAIError):
    """Raised when attempting to modify a frozen dependency graph."""

    pass
