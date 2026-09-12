"""Domain models for durable execution state, node checkpoints, and plan structural hashes."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nexusai.brain.domain.agent import PlanGraph


class ExecutionStatus(str, Enum):
    """Overall status of a persisted DAG execution."""

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CHECKPOINT = "CHECKPOINT"
    SUCCEEDED = "SUCCEEDED"
    COMPLETED = "COMPLETED"  # Backward compatibility alias for SUCCEEDED
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    FAILED = "FAILED"  # Backward compatibility alias for FAILED_TERMINAL
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class NodeExecutionStatus(str, Enum):
    """Status of an individual node checkpoint in durable storage."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RETRY_WAIT = "RETRY_WAIT"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass
class NodeExecutionRecord:
    """Durable checkpoint entity for a single PlanGraph node."""

    execution_id: str
    node_id: Any
    status: NodeExecutionStatus = NodeExecutionStatus.PENDING
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    output: Any = None
    error_message: str | None = None
    attempt_count: int = 0
    idempotency_key: str | None = None
    last_failure_class: str | None = None
    last_recovery_action: str | None = None
    next_retry_at: float | None = None
    started_at: float | None = None
    completed_at: float | None = None
    updated_at: float = field(default_factory=time.time)


@dataclass
class ExecutionRecord:
    """Durable checkpoint entity for an entire PlanGraph execution."""

    execution_id: str
    plan_id: str
    graph_hash: str
    status: ExecutionStatus = ExecutionStatus.CREATED
    schema_version: int = 3
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    node_records: dict[Any, NodeExecutionRecord] = field(default_factory=dict)
    worker_id: str | None = None
    fencing_token: int = 0
    actor: str = "system"
    tenant_id: str = "default"
    idempotency_key: str | None = None
    retry_count: int = 0
    cancellation_requested: bool = False


def compute_plan_graph_hash(plan_graph: PlanGraph) -> str:
    """Compute a deterministic SHA-256 structural & semantic hash for a PlanGraph instance."""
    normalized_nodes = []
    for node_id in sorted(plan_graph.nodes.keys(), key=lambda k: (type(k).__name__, str(k))):
        node = plan_graph.nodes[node_id]
        sorted_deps = sorted(node.dependencies, key=lambda d: (type(d).__name__, str(d)))

        # Explicit JSON serialization check for arguments: no ambiguous fallback!
        try:
            norm_args = json.dumps(node.step.arguments, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Step arguments for step {node_id} are not JSON-serializable: {exc}"
            ) from exc

        normalized_nodes.append(
            {
                "node_id": str(node_id),
                "title": str(node.step.title),
                "tool_name": str(node.step.tool_name),
                "arguments_hash": hashlib.sha256(norm_args.encode("utf-8")).hexdigest(),
                "dependencies": [str(d) for d in sorted_deps],
            }
        )

    normalized_edges = sorted([(str(parent), str(child)) for parent, child in plan_graph.edges])

    hash_payload = {
        "nodes": normalized_nodes,
        "edges": normalized_edges,
    }

    serialized = json.dumps(hash_payload, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
