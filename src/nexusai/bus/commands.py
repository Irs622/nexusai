"""
CQRS Commands & Command Handlers for NexusAI.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError

from nexusai.bus.bus import EventBus
from nexusai.bus.events import ToolExecutedEvent
from nexusai.core.errors import SecurityError, ToolExecutionError
from nexusai.infrastructure.idempotency import (
    IdempotencyState,
    IdempotencyStore,
    compute_payload_fingerprint,
)
from nexusai.infrastructure.observability.redaction import sanitize_secrets_recursive
from nexusai.security.guard import ActionRequest, SecurityGuard
from nexusai.tools.registry import ToolRegistry


class ExecuteToolCommand(BaseModel):
    """Command payload to trigger tool execution through the CQRS command bus."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    approval_token: str | None = None
    user_id: str = "anonymous"
    execution_id: str = ""
    user_confirmed: bool = False
    idempotency_key: str | None = None
    tenant_id: str = "default"


class ExecuteToolCommandHandler:
    """Handler executing tool calls with schema validation and security checks."""

    def __init__(
        self,
        registry: ToolRegistry,
        security_guard: SecurityGuard,
        event_bus: EventBus,
        idempotency_store: IdempotencyStore | None = None,
    ) -> None:
        self.registry = registry
        self.security_guard = security_guard
        self.event_bus = event_bus
        self.idempotency_store = idempotency_store

    async def __call__(self, command: ExecuteToolCommand) -> Any:
        """Process the ExecuteToolCommand with optional idempotency enforcement."""
        # 0. Check idempotency store if idempotency_key is present
        if command.idempotency_key and self.idempotency_store:
            fingerprint = compute_payload_fingerprint(
                {"tool_name": command.tool_name, "arguments": command.arguments}
            )
            record, should_execute = await self.idempotency_store.start_execution(
                tenant_id=command.tenant_id,
                user_id=command.user_id,
                idempotency_key=command.idempotency_key,
                fingerprint=fingerprint,
            )
            if not should_execute:
                if record.state == IdempotencyState.SUCCEEDED:
                    if isinstance(record.response, dict) and "output" in record.response:
                        return record.response["output"]
                    return record.response
                if record.state == IdempotencyState.FAILED_TERMINAL:
                    raise ToolExecutionError(
                        f"Cached terminal failure for tool '{command.tool_name}': {record.error_message}",
                        details={"cached": "true", "error": str(record.error_message)},
                    )

        tool = self.registry.get(command.tool_name)

        # 1. Validate arguments against Pydantic schema
        try:
            validated_args = tool.input_schema(**command.arguments)
        except ValidationError as ve:
            if command.idempotency_key and self.idempotency_store:
                await self.idempotency_store.fail_execution(
                    tenant_id=command.tenant_id,
                    user_id=command.user_id,
                    idempotency_key=command.idempotency_key,
                    error=ve,
                    state=IdempotencyState.FAILED_TERMINAL,
                )
            raise ToolExecutionError(
                f"Invalid arguments for tool '{tool.name}': {ve}",
                details={"errors": str(ve.errors())},
            ) from ve

        # 2. Convert arguments to string dict for security guard evaluation
        string_params = {k: str(v) for k, v in command.arguments.items()}
        action_request = ActionRequest(
            action_name=f"tool:{tool.name}",
            risk_level=tool.risk_level,
            description=tool.description,
            parameters=string_params,
            approval_token=command.approval_token,
            user_id=command.user_id,
            execution_id=command.execution_id,
        )

        # 3. Evaluate Security Guard authorization
        is_permitted = self.security_guard.evaluate_permission(
            action_request,
            approval_token=command.approval_token,
            user_id=command.user_id,
            execution_id=command.execution_id,
            user_confirmed=command.user_confirmed,
        )

        if not is_permitted:
            sec_err = SecurityError(
                f"Security policy denied execution of tool '{tool.name}' (Risk Level: {tool.risk_level.value}). Approval token required.",
                details={"tool_name": tool.name, "risk_level": tool.risk_level.value},
            )
            if command.idempotency_key and self.idempotency_store:
                await self.idempotency_store.fail_execution(
                    tenant_id=command.tenant_id,
                    user_id=command.user_id,
                    idempotency_key=command.idempotency_key,
                    error=sec_err,
                    state=IdempotencyState.FAILED_TERMINAL,
                )
            raise sec_err

        # 4. Execute tool logic safely
        try:
            result = await tool.execute(**validated_args.model_dump())
            sanitized_result = sanitize_secrets_recursive(result)
            await self.event_bus.publish(
                ToolExecutedEvent(
                    tool_name=tool.name,
                    arguments=command.arguments,
                    result=sanitized_result,
                    success=True,
                    user_id=command.user_id,
                )
            )
            if command.idempotency_key and self.idempotency_store:
                await self.idempotency_store.complete_execution(
                    tenant_id=command.tenant_id,
                    user_id=command.user_id,
                    idempotency_key=command.idempotency_key,
                    response={"output": sanitized_result},
                )
            return sanitized_result
        except Exception as e:
            await self.event_bus.publish(
                ToolExecutedEvent(
                    tool_name=tool.name,
                    arguments=command.arguments,
                    result=None,
                    success=False,
                    error=str(e),
                    user_id=command.user_id,
                )
            )
            if command.idempotency_key and self.idempotency_store:
                await self.idempotency_store.fail_execution(
                    tenant_id=command.tenant_id,
                    user_id=command.user_id,
                    idempotency_key=command.idempotency_key,
                    error=e,
                )
            if isinstance(e, ToolExecutionError):
                raise
            raise ToolExecutionError(f"Tool '{tool.name}' execution failed: {e}") from e
