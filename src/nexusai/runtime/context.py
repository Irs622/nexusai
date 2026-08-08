"""Structured Execution Context, Hierarchical Cancellation Token, Deadline, and Execution Budget."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from nexusai.core.annotations import stable
from nexusai.providers.exceptions import ProviderTimeoutError
from nexusai.runtime.clock import Clock, SystemClock


@stable
class CancellationToken:
    """Hierarchical token allowing cooperative task cancellation with parent-child propagation."""

    def __init__(self, parent: CancellationToken | None = None) -> None:
        self._is_cancelled = False
        self._reason: str | None = None
        self._parent = parent
        self._children: list[CancellationToken] = []

        if parent:
            parent._children.append(self)

    @property
    def is_cancelled(self) -> bool:
        if self._is_cancelled:
            return True
        if self._parent and self._parent.is_cancelled:
            return True
        return False

    @property
    def reason(self) -> str | None:
        if self._reason:
            return self._reason
        if self._parent and self._parent.reason:
            return self._parent.reason
        return None

    def cancel(self, reason: str = "Execution cancelled by user or system") -> None:
        if self._is_cancelled:
            return
        self._is_cancelled = True
        self._reason = reason

        for child in self._children:
            child.cancel(reason)

    def create_child(self) -> CancellationToken:
        return CancellationToken(parent=self)

    def throw_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise ProviderTimeoutError(f"Execution cancelled: {self.reason}")


@stable
@dataclass
class Deadline:
    """Unified Deadline container with remaining time calculations."""

    deadline_at: datetime
    clock: Clock = field(default_factory=SystemClock)

    def remaining_seconds(self) -> float:
        now_ts = self.clock.time()
        deadline_ts = self.deadline_at.timestamp()
        return max(0.0, deadline_ts - now_ts)

    def is_expired(self) -> bool:
        return self.remaining_seconds() <= 0.0

    def throw_if_expired(self) -> None:
        if self.is_expired():
            raise ProviderTimeoutError(f"Execution deadline of {self.deadline_at} has expired.")


@stable
@dataclass
class ExecutionBudget:
    """Structured resource budget for an execution task."""

    token_budget: int | None = None
    money_budget: float | None = None
    time_budget: float | None = None
    tool_budget: int | None = None
    retry_budget: int | None = None


@stable
@dataclass
class RequestContext:
    """Request identity metadata."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None
    user_id: str | None = None


@stable
@dataclass
class TraceContext:
    """Distributed tracing metadata."""

    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: str | None = None
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@stable
@dataclass
class RuntimeContext:
    """Runtime execution environment specifications."""

    provider_id: str | None = None
    model: str | None = None
    cancellation_token: CancellationToken = field(default_factory=CancellationToken)


@stable
@dataclass
class ResourceContext:
    """Resource constraints, deadlines, and budgets."""

    budget: ExecutionBudget = field(default_factory=ExecutionBudget)
    deadline: Deadline | None = None


@stable
@dataclass
class ExecutionContext:
    """Structured Execution Context aggregating Request, Trace, Runtime, and Resource contexts."""

    request: RequestContext = field(default_factory=RequestContext)
    trace: TraceContext = field(default_factory=TraceContext)
    runtime: RuntimeContext = field(default_factory=RuntimeContext)
    resource: ResourceContext = field(default_factory=ResourceContext)
    scratchpad: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@stable
@dataclass
class ExecutionHandle:
    """Handle for monitoring and controlling a running asynchronous task."""

    task_id: str
    context: ExecutionContext

    def cancel(self, reason: str = "Cancelled via ExecutionHandle") -> None:
        self.context.runtime.cancellation_token.cancel(reason)

    @property
    def is_cancelled(self) -> bool:
        return self.context.runtime.cancellation_token.is_cancelled
