"""SecurityGuard Policy Orchestrator and Risk Level Evaluator."""

from __future__ import annotations

import re
import shlex
import time
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from nexusai.core.config import SecuritySettings

from nexusai.core.errors import SecurityError
from nexusai.logging.logger import log_audit
from nexusai.security.approval_token import ApprovalTokenService
from nexusai.security.authorization import RbacEngine
from nexusai.security.capability import CapabilityResolver
from nexusai.security.identity import Identity, Role, TenantContext
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


def extract_command_binaries(command_str: str) -> list[str]:
    """Extract all distinct command binaries invoked in a shell command string.

    Deconstructs command chains, pipes, conditional operators, background tokens,
    subshells, and environment variable prefixes to prevent injection or chaining bypasses.
    """
    if not command_str or not command_str.strip():
        return []

    # 1. Extract subshell contents from $(...) and `...`
    sub_cmds: list[str] = []
    for sub in re.findall(r"\$\((.*?)\)", command_str):
        sub_cmds.append(sub)
    for sub in re.findall(r"`(.*?)`", command_str):
        sub_cmds.append(sub)

    # Clean subshell expressions from main command
    clean_main = re.sub(r"\$\(.*?\)", " ", command_str)
    clean_main = re.sub(r"`.*?`", " ", clean_main)

    all_chunks = [clean_main] + sub_cmds
    binaries: list[str] = []
    separator_pattern = re.compile(r";|&&|\|\||\||&|\n")

    for chunk in all_chunks:
        segments = separator_pattern.split(chunk)
        for seg in segments:
            seg = seg.strip().strip("()")
            if not seg:
                continue

            try:
                tokens = shlex.split(seg)
            except Exception:
                tokens = seg.split()

            if not tokens:
                continue

            idx = 0
            # Skip environment variable assignments (KEY=VAL)
            while idx < len(tokens) and "=" in tokens[idx] and not tokens[idx].startswith("-"):
                idx += 1

            if idx >= len(tokens):
                continue

            token = tokens[idx]
            wrappers = {"env", "sudo", "nohup", "timeout", "nice", "xargs"}
            base_token = Path(token).name
            binaries.append(base_token)

            if base_token in wrappers and idx + 1 < len(tokens):
                next_idx = idx + 1
                while next_idx < len(tokens) and tokens[next_idx].startswith("-"):
                    next_idx += 1
                if base_token == "timeout" and next_idx < len(tokens):
                    try:
                        float(tokens[next_idx])
                        next_idx += 1
                    except ValueError:
                        pass
                if next_idx < len(tokens):
                    binaries.append(Path(tokens[next_idx]).name)

    seen: set[str] = set()
    result: list[str] = []
    for b in binaries:
        b_clean = b.strip("'\"")
        if b_clean and b_clean not in seen:
            seen.add(b_clean)
            result.append(b_clean)
    return result


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
        capability_resolver: CapabilityResolver | None = None,
        human_approval_engine: Any | None = None,
    ) -> None:
        self.settings = settings
        self.sanitizer = InputSanitizer(
            forbidden_commands=settings.forbidden_commands,
            protected_paths=settings.protected_paths,
        )
        self.approval_service = approval_service or ApprovalTokenService()
        self.auth_middleware = auth_middleware
        self.rbac_engine = rbac_engine or RbacEngine()
        self.capability_resolver = (
            capability_resolver
            if capability_resolver is not None
            else CapabilityResolver.from_yaml("config/capabilities.yaml")
        )
        self.human_approval_engine = human_approval_engine

    def _map_request_to_capability(
        self, request: ActionRequest
    ) -> tuple[str, str, str, dict[str, Any]]:
        """Map an ActionRequest to capability domain, action, resource, and execution context."""
        action_name = request.action_name
        params = request.parameters
        context: dict[str, Any] = dict(params)

        tool_name = action_name.removeprefix("tool:")

        # 1. Shell domain
        if tool_name in ("execute_terminal", "terminal"):
            cmd = params.get("command", "")
            binary = cmd.strip().split()[0] if cmd.strip() else "*"
            context["command"] = cmd
            if "timeout" in params:
                context["duration_seconds"] = float(params["timeout"])
            elif "timeout_seconds" in params:
                context["duration_seconds"] = float(params["timeout_seconds"])
            return "shell", "execute", binary, context

        # 2. Filesystem domain
        if tool_name in ("workspace_read_file", "read_file"):
            target_path = params.get("file_path", params.get("path", "*"))
            context["path"] = target_path
            return "filesystem", "read", target_path, context

        if tool_name in ("workspace_write_file", "write_file"):
            target_path = params.get("file_path", params.get("path", "*"))
            context["path"] = target_path
            return "filesystem", "write", target_path, context

        if tool_name in ("workspace_list_directory", "list_directory"):
            target_path = params.get("path", "*")
            context["path"] = target_path
            return "filesystem", "list", target_path, context

        # 3. Network domain
        if tool_name in ("network_tool", "fetch_url", "http_request") or "url" in params:
            url = params.get("url", "")
            import urllib.parse

            parsed = urllib.parse.urlparse(url)
            host = parsed.hostname or url or "*"
            context["url"] = url
            context["host"] = host
            method = params.get("method", "GET").upper()
            action = "http_get" if method == "GET" else "http_post"
            return "network", action, host, context

        # 4. MCP domain
        if tool_name.startswith("mcp_") or "server_name" in params:
            mcp_resource = params.get("tool_name") or tool_name.removeprefix("mcp_")
            return "mcp", "invoke", mcp_resource, context

        # 5. Memory domain
        if tool_name.startswith("memory_") or "memory" in tool_name:
            action = "read" if "read" in tool_name or "search" in tool_name else "write"
            ns = params.get("namespace", "*")
            return "memory", action, ns, context

        # 6. Applescript domain
        if "applescript" in tool_name or "osascript" in tool_name:
            app = params.get("app", "*")
            return "applescript", "execute", app, context

        # Default tool execution fallback
        return "tool", "execute", tool_name, context

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
        3. Fine-grained Capability resolution (positive default-deny check).
        4. Sanitizer validation for commands and paths.
        5. Approval check based on risk level and approval token validity.

        Returns:
            True if action is permitted.

        Raises:
            SecurityError: If an explicit security policy violation, forbidden pattern,
                tampered path, or invalid/replayed/expired approval token occurs.
        """
        ambient_identity = TenantContext.get_current_identity()
        eff_token = approval_token or request.approval_token
        eff_user_id = user_id if user_id != "anonymous" else request.user_id
        if eff_user_id == "anonymous" and ambient_identity is not None:
            eff_user_id = ambient_identity.user_id
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
            if not self.rbac_engine.check_permission(
                eff_user_id, request.action_name, request.risk_level
            ):
                log_audit(
                    "ACTION_DENIED_RBAC", {"action": request.action_name, "user": eff_user_id}
                )
                return False

        # 3. Capability resolution gate (#34 positive capability check)
        if self.capability_resolver is not None:
            identity = TenantContext.get_current_identity()
            if identity is None:
                # Backwards-compatible ambient fallback when invoked outside HTTP middleware
                identity = Identity(
                    tenant_id="default",
                    user_id=eff_user_id,
                    role=(
                        Role.ADMIN
                        if eff_user_id in ("admin", "system", "anonymous")
                        else Role.OPERATOR
                    ),
                )

            domain, cap_action, resource, cap_context = self._map_request_to_capability(request)

            # For shell execution, evaluate EVERY command binary in the pipeline/chain
            if domain == "shell" and cap_action == "execute":
                cmd_str = str(cap_context.get("command", ""))
                binaries = extract_command_binaries(cmd_str)
                if not binaries:
                    binaries = [resource]

                for bin_name in binaries:
                    bin_ctx = dict(cap_context)
                    bin_ctx["command"] = bin_name
                    is_allowed, matched_cap, denial_reason = self.capability_resolver.evaluate(
                        identity, "shell", "execute", bin_name, bin_ctx
                    )
                    if not is_allowed:
                        log_audit(
                            "ACTION_DENIED_CAPABILITY",
                            {
                                "action": request.action_name,
                                "user": identity.user_id,
                                "domain": "shell",
                                "capability_action": "execute",
                                "resource": bin_name,
                                "reason": denial_reason
                                or f"Shell command '{bin_name}' denied by capability policy",
                            },
                        )
                        raise SecurityError(
                            f"Capability access denied for shell command '{bin_name}': {denial_reason}",
                            details={
                                "user_id": identity.user_id,
                                "domain": "shell",
                                "action": "execute",
                                "resource": bin_name,
                                "reason": denial_reason or "Access denied by capability policy",
                            },
                        )
            else:
                is_allowed, matched_cap, denial_reason = self.capability_resolver.evaluate(
                    identity, domain, cap_action, resource, cap_context
                )
                if not is_allowed:
                    log_audit(
                        "ACTION_DENIED_CAPABILITY",
                        {
                            "action": request.action_name,
                            "user": identity.user_id,
                            "domain": domain,
                            "capability_action": cap_action,
                            "resource": resource,
                            "reason": denial_reason or "Access denied by capability policy",
                        },
                    )
                    raise SecurityError(
                        f"Capability access denied: {denial_reason}",
                        details={
                            "user_id": identity.user_id,
                            "domain": domain,
                            "action": cap_action,
                            "resource": resource,
                            "reason": denial_reason or "Access denied by capability policy",
                        },
                    )

            log_audit(
                "ACTION_PERMITTED_BY_CAPABILITY",
                {
                    "action": request.action_name,
                    "user": identity.user_id,
                    "domain": domain,
                    "resource": resource,
                },
            )

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
