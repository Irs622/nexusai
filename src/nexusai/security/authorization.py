"""Role-Based Access Control (RBAC) Engine for NexusAI."""

from __future__ import annotations

from typing import Any

from nexusai.core.errors import AuthorizationError
from nexusai.security.identity import ROLE_HIERARCHY, Identity, Role, TenantContext


class RbacEngine:
    """Enforces role-based permissions, tool execution boundaries, and anti-escalation policies."""

    def __init__(self) -> None:
        """Initialize RbacEngine."""
        pass

    def check_tool_access(self, identity: Identity, risk_level: Any) -> bool:
        """Determine if identity is authorized to execute a tool with the given risk level.

        Matrix:
        - VIEWER: Denied for all tool executions.
        - OPERATOR: Permitted for LOW and MEDIUM risk tools; denied for HIGH and CRITICAL.
        - ADMIN / SYSTEM: Permitted for all risk levels.
        """
        # Normalizing risk string
        risk_str = str(risk_level.value if hasattr(risk_level, "value") else risk_level).upper()

        if identity.role == Role.VIEWER:
            return False

        if identity.role == Role.OPERATOR:
            if risk_str in ("LOW", "MEDIUM"):
                return True
            return False

        if identity.role in (Role.ADMIN, Role.SYSTEM):
            return True

        return False

    def check_http_access(self, identity: Identity, method: str, path: str) -> bool:
        """Determine whether identity role permits the given HTTP method and path.

        Matrix:
        - VIEWER: Can only perform read-only requests (GET, HEAD, OPTIONS).
        - OPERATOR / ADMIN / SYSTEM: Permitted general HTTP mutations.
        """
        method_upper = method.upper()

        if identity.role == Role.VIEWER:
            # Viewer can only read
            if method_upper in ("GET", "HEAD", "OPTIONS"):
                return True
            return False

        return True

    def check_permission(
        self,
        user_or_identity: str | Identity,
        action_name: str,
        risk_level: Any | None = None,
    ) -> bool:
        """Integration hook for SecurityGuard.check_permission.

        Args:
            user_or_identity: Caller identifier or Identity object.
            action_name: Target action or tool identifier.
            risk_level: Optional risk classification.

        Returns:
            True if permitted by RBAC policy, False otherwise.
        """
        identity: Identity | None = None
        if isinstance(user_or_identity, Identity):
            identity = user_or_identity
        else:
            identity = TenantContext.get_current_identity()

        if identity is None:
            # If no ambient identity context is established, default to permitting
            # so legacy/internal non-HTTP callers without identity are governed by downstream guards
            return True

        if action_name.startswith("tool:"):
            if risk_level is not None:
                return self.check_tool_access(identity, risk_level)
            if identity.role == Role.VIEWER:
                return False

        return True

    def validate_role_assignment(
        self,
        actor: Identity,
        target_role: Role,
        target_user_id: str | None = None,
    ) -> bool:
        """Enforce anti-escalation invariant: callers cannot assign or elevate to roles higher than their own.

        Args:
            actor: Calling authenticated identity.
            target_role: The role being assigned or modified.
            target_user_id: Optional user ID receiving the role.

        Returns:
            True if assignment is permitted.

        Raises:
            AuthorizationError: If role escalation attempt is detected.
        """
        actor_level = ROLE_HIERARCHY.get(actor.role, 0)
        target_level = ROLE_HIERARCHY.get(target_role, 0)

        # Non-admin / non-system callers cannot modify or assign roles at all
        if actor.role in (Role.VIEWER, Role.OPERATOR):
            raise AuthorizationError(
                f"Role escalation denied: Role '{actor.role.value}' cannot manage or assign roles",
                details={"actor_role": actor.role.value, "target_role": target_role.value},
            )

        # Actor cannot assign a role higher than their own level
        if target_level > actor_level:
            raise AuthorizationError(
                f"Role escalation denied: Cannot assign role '{target_role.value}' exceeding caller role '{actor.role.value}'",
                details={"actor_role": actor.role.value, "target_role": target_role.value},
            )

        # Actor cannot modify their own role to escalate
        if target_user_id and target_user_id == actor.user_id and target_level > actor_level:
            raise AuthorizationError(
                f"Role escalation denied: User '{actor.user_id}' cannot elevate own role",
                details={"actor": actor.user_id, "target_role": target_role.value},
            )

        return True
