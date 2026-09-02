"""Domain entities and contracts for Agent-to-Agent (A2A) Collaboration Mesh."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Mapping
from uuid import uuid4


class AgentRole(str, Enum):
    """Specialized functional roles in the agent collaboration mesh."""

    ORCHESTRATOR = "ORCHESTRATOR"
    PLANNER = "PLANNER"
    CODER = "CODER"
    AUDITOR = "AUDITOR"


class A2AMessageType(str, Enum):
    """Semantic classifications for inter-agent messages."""

    TASK_DELEGATION = "TASK_DELEGATION"
    PROPOSAL = "PROPOSAL"
    REVIEW_FEEDBACK = "REVIEW_FEEDBACK"
    CONSENSUS_REACHED = "CONSENSUS_REACHED"
    BROADCAST = "BROADCAST"


class ReviewVerdict(str, Enum):
    """Auditor evaluation outcome for a proposed artifact or code solution."""

    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class A2AMessage:
    """Standard envelope for inter-agent message passing within the collaboration mesh."""

    sender_id: str
    sender_role: AgentRole
    recipient_id: str  # specific agent_id or '*' for mesh broadcast
    message_type: A2AMessageType
    conversation_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: f"msg-{uuid4().hex[:8]}")
    timestamp: float = field(default_factory=time.time)

    def is_broadcast(self) -> bool:
        """Return True if message is targeted to all mesh agents."""
        return self.recipient_id == "*"


@dataclass(frozen=True)
class CollaborationResult:
    """Outcome of a completed multi-agent collaboration and negotiation session."""

    task_id: str
    goal: str
    final_status: str
    rounds_count: int
    dialogue_history: tuple[A2AMessage, ...]
    artifact_outputs: Mapping[str, Any]
    is_approved: bool
    summary: str = ""
