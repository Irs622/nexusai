"""Seed data for NexusAI Studio simulation endpoints (audit chain, plans, governance)."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from nexusai.brain.domain.audit import GENESIS_HASH, AuditEvent

# Import Tools & MCP


def _compute_audit_event_hash(event: AuditEvent) -> str:
    """Compute the expected SHA-256 event hash matching AuditEvent.__post_init__ canonical format."""
    canonical_payload = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "session_id": event.session_id,
        "execution_id": event.execution_id,
        "plan_fingerprint": event.plan_fingerprint,
        "sequence_number": event.sequence_number,
        "timestamp": event.timestamp,
        "node_id": event.node_id,
        "tool_id": event.tool_id,
        "worker_id": event.worker_id,
        "fencing_token": event.fencing_token,
        "actor": event.actor,
        "tenant_id": event.tenant_id,
        "outcome": event.outcome,
        "severity": event.severity,
        "previous_event_hash": event.previous_event_hash,
    }
    raw_bytes = json.dumps(canonical_payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw_bytes).hexdigest()


def _create_initial_audit_chain() -> list[AuditEvent]:
    """Generate initial verified cryptographic audit chain starting from GENESIS_HASH."""
    now = time.time()
    chain: list[AuditEvent] = []

    ev1 = AuditEvent(
        event_id="evt-genesis-101",
        event_type="WORKFLOW_INITIALIZED",
        session_id="studio-session-1",
        execution_id="exec-dag-studio-1",
        plan_fingerprint="fp-incident-remediation-v1",
        sequence_number=1,
        timestamp=now - 25.0,
        node_id="step_1",
        tool_id="system_init",
        worker_id="worker-mac-01",
        actor="autonomous-agent",
        outcome="SUCCESS",
        severity="INFO",
        previous_event_hash=GENESIS_HASH,
        metadata={"scope": "studio-demo"},
    )
    chain.append(ev1)

    ev2 = AuditEvent(
        event_id="evt-dag-102",
        event_type="DAG_PLAN_COMPILED",
        session_id="studio-session-1",
        execution_id="exec-dag-studio-1",
        plan_fingerprint="fp-incident-remediation-v1",
        sequence_number=2,
        timestamp=now - 20.0,
        node_id="step_2",
        tool_id="planner_engine",
        worker_id="worker-mac-01",
        actor="autonomous-agent",
        outcome="SUCCESS",
        severity="INFO",
        previous_event_hash=ev1.event_hash,
        metadata={"nodes_count": 6, "algorithm": "topological_kahn"},
    )
    chain.append(ev2)

    ev3 = AuditEvent(
        event_id="evt-gov-103",
        event_type="GOVERNANCE_ADMISSION_GRANTED",
        session_id="studio-session-1",
        execution_id="exec-dag-studio-1",
        plan_fingerprint="fp-incident-remediation-v1",
        sequence_number=3,
        timestamp=now - 15.0,
        node_id="step_3",
        tool_id="governance_engine",
        worker_id="worker-mac-01",
        actor="governance-controller",
        outcome="SUCCESS",
        severity="INFO",
        previous_event_hash=ev2.event_hash,
        metadata={"budget_approved": True, "memory_mb": 512},
    )
    chain.append(ev3)

    ev4 = AuditEvent(
        event_id="evt-box-104",
        event_type="SANDBOX_CONTAINER_SPAWNED",
        session_id="studio-session-1",
        execution_id="exec-dag-studio-1",
        plan_fingerprint="fp-incident-remediation-v1",
        sequence_number=4,
        timestamp=now - 10.0,
        node_id="step_4",
        tool_id="container_runtime",
        worker_id="worker-mac-01",
        actor="container-daemon",
        outcome="SUCCESS",
        severity="INFO",
        previous_event_hash=ev3.event_hash,
        metadata={"isolation": "rootless", "network": "none"},
    )
    chain.append(ev4)

    ev5 = AuditEvent(
        event_id="evt-exec-105",
        event_type="TOOL_EXECUTION_COMPLETED",
        session_id="studio-session-1",
        execution_id="exec-dag-studio-1",
        plan_fingerprint="fp-incident-remediation-v1",
        sequence_number=5,
        timestamp=now - 5.0,
        node_id="step_5",
        tool_id="TerminalTool",
        worker_id="worker-mac-01",
        actor="tool-executor",
        outcome="SUCCESS",
        severity="INFO",
        previous_event_hash=ev4.event_hash,
        metadata={"exit_code": 0, "duration_ms": 142.5},
    )
    chain.append(ev5)

    return chain


def _create_studio_plans() -> dict[str, dict[str, Any]]:
    """Return pre-configured agent plan templates for NexusAI Studio visualization."""
    return {
        "incident_response": {
            "plan_id": "incident_response",
            "title": "Incident Response & Auto-Remediation",
            "description": "Autonomous threat detection, sandbox isolation, security hotfix, and health verification.",
            "nodes": [
                {
                    "id": "step_1",
                    "title": "Fetch System Diagnostics",
                    "tool": "TerminalTool",
                    "description": "Inspect running processes and CPU/RAM anomalies",
                    "dependencies": [],
                    "status": "COMPLETED",
                    "latency_ms": 142.0,
                    "output": {"status": "ok", "anomalies_detected": 1},
                },
                {
                    "id": "step_2",
                    "title": "Analyze Incident Logs & Root Cause",
                    "tool": "RecallFactTool",
                    "description": "Correlate error signatures with historical memory store",
                    "dependencies": ["step_1"],
                    "status": "COMPLETED",
                    "latency_ms": 98.0,
                    "output": {"root_cause": "unauthorized_container_egress"},
                },
                {
                    "id": "step_3",
                    "title": "Isolate Rogue Process in Sandbox",
                    "tool": "TerminalTool",
                    "description": "Enforce cgroup freeze and drop capabilities",
                    "dependencies": ["step_2"],
                    "status": "COMPLETED",
                    "latency_ms": 185.0,
                    "output": {"cgroups_frozen": True, "network_cut": True},
                },
                {
                    "id": "step_4",
                    "title": "Apply Security Mitigation Patch",
                    "tool": "GitStatusTool",
                    "description": "Stage emergency firewall and ACL rules",
                    "dependencies": ["step_2"],
                    "status": "COMPLETED",
                    "latency_ms": 112.0,
                    "output": {"patch_applied": "acl_rules_v4.yaml"},
                },
                {
                    "id": "step_5",
                    "title": "Verify Health & Port Integrity",
                    "tool": "GetActiveWindowTool",
                    "description": "Confirm service endpoints are listening and healthy",
                    "dependencies": ["step_3", "step_4"],
                    "status": "COMPLETED",
                    "latency_ms": 76.0,
                    "output": {"service_status": "healthy", "open_ports": [8000, 50051]},
                },
                {
                    "id": "step_6",
                    "title": "Generate Cryptographic Incident Audit Report",
                    "tool": "RememberFactTool",
                    "description": "Persist SHA-256 signed attestation to memory store",
                    "dependencies": ["step_5"],
                    "status": "COMPLETED",
                    "latency_ms": 65.0,
                    "output": {"audit_hash": "sha256:d8b2e1...", "verdict": "REMEDIATED"},
                },
            ],
            "edges": [
                ["step_1", "step_2"],
                ["step_2", "step_3"],
                ["step_2", "step_4"],
                ["step_3", "step_5"],
                ["step_4", "step_5"],
                ["step_5", "step_6"],
            ],
        },
        "vulnerability_audit": {
            "plan_id": "vulnerability_audit",
            "title": "Security Vulnerability & Sandbox Isolation Audit",
            "description": "Audit container mounts, credential redaction, cgroups limits, and attestation.",
            "nodes": [
                {
                    "id": "step_1",
                    "title": "Enumerate Host Capabilities & Sockets",
                    "tool": "TerminalTool",
                    "description": "Scan for forbidden /var/run/docker.sock mounts",
                    "dependencies": [],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_2",
                    "title": "Validate Jail Mount Path Containment",
                    "tool": "ListDirectoryTool",
                    "description": "Verify canonical path traversal prevention",
                    "dependencies": ["step_1"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_3",
                    "title": "Sanitize Host Environment Credentials",
                    "tool": "TerminalTool",
                    "description": "Redact passwords, tokens, and secret variables",
                    "dependencies": ["step_1"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_4",
                    "title": "Test Fencing Token Monotonic Invariant",
                    "tool": "TerminalTool",
                    "description": "Verify zombie worker rejection on stale token",
                    "dependencies": ["step_2", "step_3"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_5",
                    "title": "Sign & Publish Immutable Audit Proof",
                    "tool": "RememberFactTool",
                    "description": "Commit immutable record to audit log",
                    "dependencies": ["step_4"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
            ],
            "edges": [
                ["step_1", "step_2"],
                ["step_1", "step_3"],
                ["step_2", "step_4"],
                ["step_3", "step_4"],
                ["step_4", "step_5"],
            ],
        },
        "data_pipeline": {
            "plan_id": "data_pipeline",
            "title": "Semantic Memory Vector Ingestion Pipeline",
            "description": "Ingest unstructured knowledge documents, compute vector embeddings, and synchronize pgvector & Qdrant.",
            "nodes": [
                {
                    "id": "step_1",
                    "title": "Ingest Unstructured Knowledge Documents",
                    "tool": "ReadFileTool",
                    "description": "Extract text from markdown and code repository files",
                    "dependencies": [],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_2",
                    "title": "Chunk & Generate Dense Embeddings",
                    "tool": "RememberFactTool",
                    "description": "Generate 1536-dim vector embeddings",
                    "dependencies": ["step_1"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_3",
                    "title": "Index Vector Records in PostgreSQL pgvector",
                    "tool": "RememberFactTool",
                    "description": "Upsert cosine similarity index using HNSW",
                    "dependencies": ["step_2"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_4",
                    "title": "Synchronize HNSW Collection with Qdrant",
                    "tool": "RememberFactTool",
                    "description": "Replicate points to distributed Qdrant cluster",
                    "dependencies": ["step_2"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
                {
                    "id": "step_5",
                    "title": "Benchmark Cosine Similarity Recall",
                    "tool": "RecallFactTool",
                    "description": "Validate 100% vector recall accuracy",
                    "dependencies": ["step_3", "step_4"],
                    "status": "PENDING",
                    "latency_ms": 0.0,
                    "output": None,
                },
            ],
            "edges": [
                ["step_1", "step_2"],
                ["step_2", "step_3"],
                ["step_2", "step_4"],
                ["step_3", "step_5"],
                ["step_4", "step_5"],
            ],
        },
    }


def _create_initial_governance_budget() -> dict[str, Any]:
    """Return default resource quota limits and current consumption."""
    return {
        "limits": {
            "max_concurrent_tasks": 4,
            "max_cpu_seconds": 300.0,
            "max_memory_mb": 512,
            "max_subprocesses": 50,
            "max_network_requests": 50,
            "max_tool_invocations": 100,
        },
        "usage": {
            "active_tasks": 1,
            "cpu_seconds_used": 14.8,
            "memory_mb_used": 128.5,
            "subprocesses_used": 6,
            "network_requests_used": 8,
            "tool_invocations_used": 19,
        },
        "percentages": {
            "cpu": 4.9,
            "memory": 25.1,
            "subprocesses": 12.0,
            "network": 16.0,
            "tools": 19.0,
        },
    }


def _create_initial_pending_approvals() -> list[dict[str, Any]]:
    """Return list of sample pending human-in-the-loop approval requests."""
    now = time.time()
    return [
        {
            "approval_id": "app-sec-8801",
            "tool_id": "TerminalTool",
            "action_summary": "Terminate rogue container process on rootless network namespace",
            "risk_level": "CRITICAL",
            "action_digest": "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
            "expires_at": now + 480.0,
            "status": "PENDING",
            "command": "docker kill sandbox-worker-threat-9",
        },
        {
            "approval_id": "app-sec-8802",
            "tool_id": "RawAppleScriptTool",
            "action_summary": "Query active system privileges and audio master volume",
            "risk_level": "HIGH",
            "action_digest": "sha256:bf234857b1f6236b2893acab96c14e9f7831d68379201a0937a1f29b46e32d84",
            "expires_at": now + 540.0,
            "status": "PENDING",
            "command": "osascript -e 'get volume settings'",
        },
    ]
