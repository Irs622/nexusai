"""Domain models for Distributed Execution Coordination, Worker Identity, Leases, and Fencing Tokens."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import os
import time
from typing import Any, Mapping

from nexusai.brain.domain.observability import sanitize_attributes


class LeaseStatus(str, Enum):
    """Lifecycle status taxonomy for execution leases."""

    UNOWNED = "UNOWNED"
    LEASED = "LEASED"
    RENEWED = "RENEWED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


# ------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------

class CoordinationError(Exception):
    """Base exception for all distributed execution coordination errors."""

    pass


class LeaseAcquisitionError(CoordinationError):
    """Raised when acquiring an execution lease fails due to ownership conflict."""

    pass


class StaleWorkerError(CoordinationError):
    """Raised when a worker attempting an operation holds a stale lease or obsolete fencing token."""

    pass


class FencingTokenError(CoordinationError):
    """Raised when an operation is attempted with an obsolete or invalid fencing token."""

    pass


# ------------------------------------------------------------------
# Domain Models
# ------------------------------------------------------------------

@dataclass(frozen=True)
class WorkerIdentity:
    """Immutable domain representation of a runtime worker process identity."""

    worker_id: str
    process_id: int = field(default_factory=os.getpid)
    host_id: str = "host-local"
    started_at: float = field(default_factory=time.time)
    instance_nonce: str = ""

    def __post_init__(self) -> None:
        if not self.worker_id.strip():
            raise ValueError("worker_id cannot be empty")
        if not self.instance_nonce:
            nonce_bytes = f"{self.worker_id}:{self.process_id}:{self.started_at}".encode("utf-8")
            object.__setattr__(self, "instance_nonce", hashlib.sha256(nonce_bytes).hexdigest()[:16])


@dataclass(frozen=True)
class ExecutionLease:
    """Immutable domain representation of time-bounded execution ownership and fencing token."""

    lease_id: str
    execution_id: str
    session_id: str
    worker_id: str
    fencing_token: int
    acquired_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 30.0)
    status: LeaseStatus = LeaseStatus.LEASED
    audit_hash: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate lease domain invariants, compute audit hash, and sanitize metadata."""
        if not self.lease_id.strip():
            raise ValueError("lease_id cannot be empty")
        if not self.execution_id.strip():
            raise ValueError("execution_id cannot be empty")
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if not self.worker_id.strip():
            raise ValueError("worker_id cannot be empty")
        if self.fencing_token < 1:
            raise ValueError("fencing_token must be a positive integer >= 1")

        if not self.audit_hash:
            canonical_payload = {
                "lease_id": self.lease_id,
                "execution_id": self.execution_id,
                "session_id": self.session_id,
                "worker_id": self.worker_id,
                "fencing_token": self.fencing_token,
                "acquired_at": self.acquired_at,
                "expires_at": self.expires_at,
            }
            raw_bytes = json.dumps(canonical_payload, sort_keys=True).encode("utf-8")
            digest = hashlib.sha256(raw_bytes).hexdigest()
            object.__setattr__(self, "audit_hash", digest)

        sanitized = sanitize_attributes(self.metadata)
        object.__setattr__(self, "metadata", sanitized)
