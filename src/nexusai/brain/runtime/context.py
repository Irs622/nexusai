"""
ExecutionContext and modular sub-contexts establishing unified thread transport for AI OS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from nexusai.brain.domain.version import SchemaVersion
from nexusai.brain.runtime.budget import ExecutionBudget, ExecutionUsage
from nexusai.brain.runtime.state import SessionState


@dataclass(frozen=True)
class IdentityContext:
    """Session and workspace identity scope.

    Attributes:
        session_id: Target BrainSession UUID.
        conversation_id: Target Conversation UUID.
        user_id: Optional authenticated user identifier.
        workspace_id: Optional workspace or tenant identifier.
    """

    session_id: UUID = field(default_factory=uuid4)
    conversation_id: UUID = field(default_factory=uuid4)
    user_id: str | None = None
    workspace_id: str | None = None


@dataclass
class RuntimeContext:
    """Dynamic turn execution context and runtime state.

    Attributes:
        execution_id: Unique UUID for this specific execution attempt.
        turn_id: Unique UUID for the current turn exchange.
        session_state: Mutable SessionState reference.
        required_capabilities: List of required model capabilities (e.g. vision, json).
    """

    execution_id: UUID = field(default_factory=uuid4)
    turn_id: UUID = field(default_factory=uuid4)
    session_state: SessionState = field(
        default_factory=lambda: SessionState(provider_id="mock", active_model="mock-v1")
    )
    required_capabilities: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SecurityContext:
    """Security authorization context and permission scopes.

    Attributes:
        permissions: List of granted permissions for this execution thread.
        roles: Granted security roles.
    """

    permissions: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)


@dataclass
class TelemetryContext:
    """OpenTelemetry tracing context and metric tracking references.

    Attributes:
        trace_id: OpenTelemetry trace ID.
        span_id: Current active span ID.
        metadata: Diagnostic trace metadata.
    """

    trace_id: str = field(default_factory=lambda: uuid4().hex)
    span_id: str = field(default_factory=lambda: uuid4().hex[:16])
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CancellationContext:
    """Turn timeout and cancellation token tracking context.

    Attributes:
        deadline: Optional UTC expiration deadline for turn execution.
        is_cancelled: Boolean indicating whether turn cancellation has been signaled.
    """

    deadline: datetime | None = None
    is_cancelled: bool = False

    def check_cancelled(self) -> None:
        """Check if execution deadline has passed or cancellation was triggered."""
        if self.is_cancelled:
            return
        if self.deadline is not None and datetime.now(timezone.utc) >= self.deadline:
            self.is_cancelled = True


@dataclass
class ExecutionContext:
    """Unified container transporting thread execution state across stages.

    Follows a top-down DAG dependency structure:
    Identity -> Runtime -> Security -> Budget -> Cancellation / Telemetry.

    Attributes:
        context_version: Schema contract version.
        identity: Session identity sub-context.
        runtime: Dynamic execution sub-context.
        security: Permission sub-context.
        telemetry: Tracing & metrics sub-context.
        cancellation: Timeout & cancellation sub-context.
        budget: Resource limits configuration.
        usage: Real-time resource consumption counters.
    """

    context_version: SchemaVersion = field(default_factory=SchemaVersion)
    identity: IdentityContext = field(default_factory=IdentityContext)
    runtime: RuntimeContext = field(default_factory=RuntimeContext)
    security: SecurityContext = field(default_factory=SecurityContext)
    telemetry: TelemetryContext = field(default_factory=TelemetryContext)
    cancellation: CancellationContext = field(default_factory=CancellationContext)
    budget: ExecutionBudget = field(default_factory=ExecutionBudget)
    usage: ExecutionUsage = field(default_factory=ExecutionUsage)
