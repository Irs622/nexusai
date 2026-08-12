"""Domain models, Risk Evaluator, ActionBinding contracts, and ApprovalGrant taxonomy for P3-6 Human Approval Safety Boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import time
from typing import Any, Mapping

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.observability import sanitize_attributes


class RiskLevel(str, Enum):
    """Action risk classification levels in hierarchical precedence order: CRITICAL > HIGH > MEDIUM > LOW."""

    LOW = "LOW"            # e.g., read-only file queries
    MEDIUM = "MEDIUM"        # e.g., local file writes
    HIGH = "HIGH"          # e.g., process execution, external network calls
    CRITICAL = "CRITICAL"    # e.g., system control, secret access, destructive deletion


class ApprovalStatus(str, Enum):
    """Lifecycle state machine status for Human Approval Requests."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    CONSUMED = "CONSUMED"


TERMINAL_APPROVAL_STATUSES = frozenset({
    ApprovalStatus.APPROVED,
    ApprovalStatus.DENIED,
    ApprovalStatus.EXPIRED,
    ApprovalStatus.CANCELLED,
    ApprovalStatus.CONSUMED,
})


# ------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------

class ApprovalError(Exception):
    """Base exception for all human approval domain errors."""

    pass


class ApprovalExpiredError(ApprovalError):
    """Raised when verifying or consuming an expired approval request/grant."""

    pass


class ApprovalReplayError(ApprovalError):
    """Raised when attempting to re-use or re-consume a single-use approval grant."""

    pass


class ApprovalMismatchError(ApprovalError):
    """Raised when an approval grant's binding or action digest does not match expected execution parameters."""

    pass


class ApprovalCancelledError(ApprovalError):
    """Raised when attempting to act on a request whose execution was cancelled."""

    pass


# ------------------------------------------------------------------
# Action Binding & Canonical Digest Helpers
# ------------------------------------------------------------------

@dataclass(frozen=True)
class ActionBinding:
    """Immutable contract binding an approval request to an exact execution action."""

    session_id: str
    execution_id: str
    plan_fingerprint: str
    node_id: str
    tool_id: str
    tool_version: str
    requested_capabilities: frozenset[ToolCapability]
    resource_scope: str = "/"
    action_digest: str = ""

    def __post_init__(self) -> None:
        """Compute canonical SHA-256 action digest over all binding parameters."""
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if not self.execution_id.strip():
            raise ValueError("execution_id cannot be empty")
        if not self.plan_fingerprint.strip():
            raise ValueError("plan_fingerprint cannot be empty")
        if not self.node_id.strip():
            raise ValueError("node_id cannot be empty")
        if not self.tool_id.strip():
            raise ValueError("tool_id cannot be empty")

        if not self.action_digest:
            caps_sorted = sorted([c.value for c in self.requested_capabilities])
            canonical_payload = {
                "session_id": self.session_id,
                "execution_id": self.execution_id,
                "plan_fingerprint": self.plan_fingerprint,
                "node_id": self.node_id,
                "tool_id": self.tool_id,
                "tool_version": self.tool_version,
                "capabilities": caps_sorted,
                "resource_scope": self.resource_scope,
            }
            raw_bytes = json.dumps(canonical_payload, sort_keys=True).encode("utf-8")
            digest = hashlib.sha256(raw_bytes).hexdigest()
            object.__setattr__(self, "action_digest", digest)


@dataclass(frozen=True)
class HumanApprovalRequest:
    """Immutable domain representation of a human safety approval request."""

    approval_id: str
    binding: ActionBinding
    risk_level: RiskLevel
    prompt_summary: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate domain invariants and sanitize secret metadata/summaries."""
        if not self.approval_id.strip():
            raise ValueError("approval_id cannot be empty")
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("expires_at must be greater than created_at")

        # Secret sanitization invariant across summary and metadata
        sanitized_summary = sanitize_attributes({"summary": self.prompt_summary})["summary"]
        object.__setattr__(self, "prompt_summary", sanitized_summary)

        sanitized_meta = sanitize_attributes(self.metadata)
        object.__setattr__(self, "metadata", sanitized_meta)


@dataclass(frozen=True)
class HumanApprovalDecision:
    """Immutable human decision payload submitted by operator."""

    approval_id: str
    status: ApprovalStatus  # APPROVED or DENIED
    actor: str
    reason: str
    decision_timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.status not in (ApprovalStatus.APPROVED, ApprovalStatus.DENIED):
            raise ValueError("Decision status must be APPROVED or DENIED")
        if not self.actor.strip():
            raise ValueError("actor identifier cannot be empty")

        # Secret sanitization on decision reason
        sanitized_reason = sanitize_attributes({"reason": self.reason})["reason"]
        object.__setattr__(self, "reason", sanitized_reason)


@dataclass(frozen=True)
class ApprovalGrant:
    """Immutable, single-use security authorization grant issued upon operator approval."""

    grant_id: str
    approval_id: str
    binding: ActionBinding
    issued_at: float
    expires_at: float
    actor: str
    consumed_at: float | None = None
    audit_hash: str = ""

    def __post_init__(self) -> None:
        """Compute canonical SHA-256 audit hash over approval grant parameters."""
        if not self.audit_hash:
            canonical_payload = {
                "grant_id": self.grant_id,
                "approval_id": self.approval_id,
                "action_digest": self.binding.action_digest,
                "actor": self.actor,
                "issued_at": self.issued_at,
                "expires_at": self.expires_at,
            }
            raw_bytes = json.dumps(canonical_payload, sort_keys=True).encode("utf-8")
            digest = hashlib.sha256(raw_bytes).hexdigest()
            object.__setattr__(self, "audit_hash", digest)


# ------------------------------------------------------------------
# Risk Evaluator Precedence Function
# ------------------------------------------------------------------

CAPABILITY_RISK_MAP = {
    ToolCapability.FILE_READ: RiskLevel.LOW,
    ToolCapability.FILE_WRITE: RiskLevel.MEDIUM,
    ToolCapability.PROCESS_EXEC: RiskLevel.HIGH,
    ToolCapability.NETWORK_ACCESS: RiskLevel.HIGH,
    ToolCapability.SYSTEM_CONTROL: RiskLevel.CRITICAL,
    ToolCapability.SECRET_ACCESS: RiskLevel.CRITICAL,
}

RISK_ORDER = {
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}


def evaluate_action_risk(capabilities: frozenset[ToolCapability]) -> RiskLevel:
    """Evaluate Action Risk using strict precedence: CRITICAL > HIGH > MEDIUM > LOW."""
    if not capabilities:
        return RiskLevel.LOW

    max_rank = 0
    highest_risk = RiskLevel.LOW

    for cap in capabilities:
        risk = CAPABILITY_RISK_MAP.get(cap, RiskLevel.MEDIUM)
        rank = RISK_ORDER[risk]
        if rank > max_rank:
            max_rank = rank
            highest_risk = risk

    return highest_risk
