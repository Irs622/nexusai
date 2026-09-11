"""SecurityGuard Policy Orchestrator and Risk Level Evaluator."""

from __future__ import annotations

import time
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from nexusai.core.config import SecuritySettings

from nexusai.core.errors import SecurityError
from nexusai.logging.logger import log_audit
from nexusai.security.approval_token import ApprovalTokenService
from nexusai.security.sanitizer import InputSanitizer


class RiskLevel(str, Enum):
    LOW = "LOW"  # Read-only information checks
    MEDIUM = "MEDIUM"  # Non-destructive side effects (open app, speak)
    HIGH = "HIGH"  # Potentially modifying actions (file edit, terminal execution)
    CRITICAL = "CRITICAL"  # Destructive actions (delete file, system settings edit)


class ActionRequest(BaseModel):
    action_name: str
    risk_level: RiskLevel
    description: str
    parameters: dict[str, str] = Field(default_factory=dict)
    approval_token: str | None = None
    user_id: str = "anonymous"
    execution_id: str = ""


class SecurityGuard:
    """Evaluates security permissions, sanitizes inputs, and orchestrates security policy checks.

    Acts as the central policy orchestrator delegating to specialized components in sequence:
    Identity / Auth -> RBAC -> Capability Resolver -> Sanitizers -> Approval Token Verification.
    """

    def __init__(
        self,
        settings: SecuritySettings,
        approval_service: ApprovalTokenService | None = None,
        auth_middleware: Any | None = None,
        rbac_engine: Any | None = None,
        capability_resolver: Any | None = None,
        human_approval_engine: Any | None = None,
    ) -> None:
        self.settings = settings
        self.sanitizer = InputSanitizer(
            forbidden_commands=settings.forbidden_commands,
            protected_paths=settings.protected_paths,
        )
        self.approval_service = approval_service or ApprovalTokenService()
        self.auth_middleware = auth_middleware
        self.rbac_engine = rbac_engine
        self.capability_resolver = capability_resolver
        self.human_approval_engine = human_approval_engine

    def evaluate_permission(
        self,
        request: ActionRequest,
        approval_token: str | None = None,
        user_id: str = "anonymous",
        execution_id: str = "",
        user_confirmed: bool = False,
    ) -> bool:
        """Determine if an action is permitted by orchestrating policy gates.

        Flow:
        1. Auth / Identity validation (if configured).
        2. RBAC role permissions check (if configured).
        3. Fine-grained Capability resolution (if configured).
        4. Sanitizer validation for commands and paths.
        5. Approval check based on risk level and approval token validity.

        Returns:
            True if action is permitted.

        Raises:
            SecurityError: If an explicit security policy violation, forbidden pattern,
                tampered path, or invalid/replayed/expired approval token occurs.
        """
        eff_token = approval_token or request.approval_token
        eff_user_id = user_id if user_id != "anonymous" else request.user_id
        eff_execution_id = execution_id or request.execution_id

        # 1. Identity & Auth gate (#31 hook)
        if self.auth_middleware is not None and hasattr(self.auth_middleware, "validate_identity"):
            if not self.auth_middleware.validate_identity(eff_user_id):
                log_audit(
                    "ACTION_DENIED_AUTH", {"action": request.action_name, "user": eff_user_id}
                )
                return False

        # 2. RBAC gate (#31 hook)
        if self.rbac_engine is not None and hasattr(self.rbac_engine, "check_permission"):
            if not self.rbac_engine.check_permission(eff_user_id, request.action_name):
                log_audit(
                    "ACTION_DENIED_RBAC", {"action": request.action_name, "user": eff_user_id}
                )
                return False

        # 3. Capability resolution gate (#34 hook)
        if self.capability_resolver is not None and hasattr(
            self.capability_resolver, "is_permitted"
        ):
            if not self.capability_resolver.is_permitted(eff_user_id, request):
                log_audit(
                    "ACTION_DENIED_CAPABILITY",
                    {"action": request.action_name, "user": eff_user_id},
                )
                return False

        # 4. Input Sanitizer verification
        if "command" in request.parameters:
            self.sanitizer.validate_command(request.parameters["command"])
        if "path" in request.parameters:
            self.sanitizer.validate_path(request.parameters["path"])

        # 5. Risk-level & Approval Policy
        if request.risk_level == RiskLevel.LOW:
            log_audit("ACTION_PERMITTED", {"action": request.action_name, "risk": "LOW"})
            return True

        if request.risk_level == RiskLevel.MEDIUM:
            if self.settings.auto_approve_low_risk:
                log_audit("ACTION_PERMITTED", {"action": request.action_name, "risk": "MEDIUM"})
                return True

            # If auto-approval is disabled, require valid token or permissive non-strict mode
            if eff_token:
                tool_name = request.action_name.removeprefix("tool:")
                try:
                    self.approval_service.validate_and_consume(
                        token=eff_token,
                        tool_name=tool_name,
                        arguments=request.parameters,
                        user_id=eff_user_id,
                        execution_id=eff_execution_id,
                    )
                    log_audit(
                        "ACTION_PERMITTED_BY_TOKEN",
                        {"action": request.action_name, "risk": "MEDIUM"},
                    )
                    return True
                except Exception:
                    pass

            if not self.settings.strict_mode and user_confirmed:
                log_audit(
                    "ACTION_PERMITTED_BY_USER",
                    {"action": request.action_name, "risk": "MEDIUM"},
                )
                return True

            log_audit(
                "ACTION_REQUIRES_CONFIRMATION",
                {"action": request.action_name, "risk": "MEDIUM"},
            )
            return False

        if request.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            tool_name = request.action_name.removeprefix("tool:")

            # If approval token is provided, delegate verification to ApprovalTokenService
            if eff_token:
                # Support HumanApprovalEngine grant if token starts with grant-
                if eff_token.startswith("grant-") and self.human_approval_engine is not None:
                    engine = self.human_approval_engine
                    if hasattr(engine, "_grants"):
                        grant = engine._grants.get(eff_token)
                        if grant is None:
                            raise SecurityError(
                                f"Approval grant '{eff_token}' not found",
                                details={"token": eff_token, "tool_name": tool_name},
                            )
                        if getattr(grant, "consumed_at", None) is not None:
                            raise SecurityError(
                                f"Approval grant '{eff_token}' has already been consumed (replay detected)",
                                details={"token": eff_token, "tool_name": tool_name},
                            )
                        now = time.time()
                        if now >= getattr(grant, "expires_at", float("inf")):
                            raise SecurityError(
                                f"Approval grant '{eff_token}' has expired",
                                details={"token": eff_token, "tool_name": tool_name},
                            )
                        binding = getattr(grant, "binding", None)
                        if binding:
                            binding_tool = getattr(binding, "tool_id", None) or getattr(
                                binding, "action_name", None
                            )
                            if (
                                binding_tool
                                and binding_tool != tool_name
                                and binding_tool != request.action_name
                            ):
                                raise SecurityError(
                                    f"Action binding mismatch: grant is for '{binding_tool}' but tool is '{tool_name}'",
                                    details={"token": eff_token, "tool_name": tool_name},
                                )
                        # Mark consumed to prevent replay
                        try:
                            from nexusai.brain.domain.human_approval import ApprovalGrant

                            engine._grants[eff_token] = ApprovalGrant(
                                grant_id=grant.grant_id,
                                approval_id=grant.approval_id,
                                binding=grant.binding,
                                issued_at=grant.issued_at,
                                expires_at=grant.expires_at,
                                actor=grant.actor,
                                consumed_at=now,
                            )
                        except Exception:
                            pass
                    log_audit(
                        "ACTION_PERMITTED_BY_GRANT",
                        {"action": request.action_name, "risk": request.risk_level.value},
                    )
                    return True

                self.approval_service.validate_and_consume(
                    token=eff_token,
                    tool_name=tool_name,
                    arguments=request.parameters,
                    user_id=eff_user_id,
                    execution_id=eff_execution_id,
                )
                log_audit(
                    "ACTION_PERMITTED_BY_TOKEN",
                    {"action": request.action_name, "risk": request.risk_level.value},
                )
                return True

            # In non-strict mode only, allow legacy user_confirmed flag
            if not self.settings.strict_mode and user_confirmed:
                log_audit(
                    "ACTION_PERMITTED_BY_USER",
                    {"action": request.action_name, "risk": request.risk_level.value},
                )
                return True

            log_audit(
                "ACTION_REQUIRES_CONFIRMATION",
                {"action": request.action_name, "risk": request.risk_level.value},
            )
            return False

        return False
