"""Request schemas for the NexusAI HTTP API."""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field


# Request Schemas
class ChatRequest(BaseModel):
    prompt: str = Field(..., description="User prompt text")
    session_id: str | None = Field(
        default=None,
        description="Optional session ID. If omitted, an unguessable server-side random session is issued.",
    )
    approval_token: str | None = Field(
        default=None, description="Optional approval token for high-risk tool execution"
    )


class ToolExecRequest(BaseModel):
    tool_name: str = Field(..., description="Name of tool to execute")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool parameters")
    execution_id: str = Field(default="", description="Optional execution context ID")


class ApprovalRequest(BaseModel):
    tool_name: str = Field(..., description="Name of tool requiring approval token")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool execution parameters")
    execution_id: str = Field(default="", description="Optional execution context ID")


class DagExecuteRequest(BaseModel):
    plan_id: str = Field(default="incident_response", description="ID of plan to execute")
    simulate_failure_step: str | None = Field(
        default=None, description="Optional step ID to simulate failure"
    )
    execution_id: str = Field(
        default_factory=lambda: f"exec-dag-{int(time.time())}", description="Execution ID"
    )
    idempotency_key: str | None = Field(
        default=None, description="Optional idempotency key for DAG execution"
    )


class AuditTamperRequest(BaseModel):
    event_id: str | None = Field(default=None, description="Target event ID to corrupt")
    tampered_field: str = Field(default="outcome", description="Field to modify")
    new_value: str = Field(default="CORRUPTED_TAMPER_TEST", description="Tampered value")


class GovernanceDecisionRequest(BaseModel):
    decision: str = Field(default="APPROVED", description="APPROVED or DENIED")
    actor: str = Field(default="security-operator", description="Operator identity")


ChatRequest.model_rebuild()
ToolExecRequest.model_rebuild()
ApprovalRequest.model_rebuild()
DagExecuteRequest.model_rebuild()
AuditTamperRequest.model_rebuild()
GovernanceDecisionRequest.model_rebuild()
