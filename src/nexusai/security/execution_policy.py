"""Object-level authorization policy for execution resources (BOLA / IDOR protection)."""

from __future__ import annotations

from nexusai.core.errors import AuthenticationError, AuthorizationError
from nexusai.security.identity import Identity, Role


class ExecutionAccessPolicy:
    """Centralized object-level authorization policy governing execution inspection and lifecycle operations.

    Enforces multi-tenant isolation invariants:
    - Cross-tenant access is strictly denied unless caller holds ADMIN or SYSTEM role.
    - VIEWER role cannot execute state mutations (such as cancellation or retry).
    - Unauthenticated callers are rejected fail-closed.
    """

    @staticmethod
    def can_read(identity: Identity | None, execution_tenant_id: str) -> bool:
        """Determine whether the caller is authorized to inspect/read the execution state.

        Args:
            identity: Authenticated caller identity.
            execution_tenant_id: Tenant owning the execution record.

        Returns:
            True if access is permitted, False otherwise.
        """
        if identity is None:
            return False

        if identity.role in (Role.ADMIN, Role.SYSTEM):
            return True

        return identity.tenant_id == execution_tenant_id

    @staticmethod
    def can_cancel(identity: Identity | None, execution_tenant_id: str) -> bool:
        """Determine whether the caller is authorized to request cancellation of an execution.

        Args:
            identity: Authenticated caller identity.
            execution_tenant_id: Tenant owning the execution record.

        Returns:
            True if cancellation is permitted, False otherwise.
        """
        if identity is None:
            return False

        # Viewers are strictly read-only and cannot mutate execution lifecycle
        if identity.role == Role.VIEWER:
            return False

        if identity.role in (Role.ADMIN, Role.SYSTEM):
            return True

        return identity.tenant_id == execution_tenant_id

    @staticmethod
    def can_mutate(identity: Identity | None, execution_tenant_id: str) -> bool:
        """Determine whether caller can perform general state mutations on the execution."""
        return ExecutionAccessPolicy.can_cancel(identity, execution_tenant_id)

    @classmethod
    def authorize_read(cls, identity: Identity | None, execution_tenant_id: str) -> None:
        """Authorize reading an execution, raising explicit domain exceptions if denied.

        Args:
            identity: Authenticated caller identity.
            execution_tenant_id: Tenant owning the execution record.

        Raises:
            AuthenticationError: If identity is unauthenticated.
            AuthorizationError: If caller lacks permissions to inspect the execution.
        """
        if identity is None:
            raise AuthenticationError("Authentication required to inspect execution state")

        if not cls.can_read(identity, execution_tenant_id):
            raise AuthorizationError(
                f"Cross-tenant execution access denied for tenant '{identity.tenant_id}'. Admin or System role required.",
                details={
                    "caller_tenant": identity.tenant_id,
                    "target_tenant": execution_tenant_id,
                    "caller_role": identity.role.value,
                },
            )

    @classmethod
    def authorize_cancel(cls, identity: Identity | None, execution_tenant_id: str) -> None:
        """Authorize cancelling an execution, raising explicit domain exceptions if denied.

        Args:
            identity: Authenticated caller identity.
            execution_tenant_id: Tenant owning the execution record.

        Raises:
            AuthenticationError: If identity is unauthenticated.
            AuthorizationError: If caller lacks permissions to cancel the execution.
        """
        if identity is None:
            raise AuthenticationError("Authentication required to cancel execution")

        if identity.role == Role.VIEWER:
            raise AuthorizationError(
                "RBAC access denied: Viewer role cannot cancel executions",
                details={"caller_role": identity.role.value},
            )

        if not cls.can_cancel(identity, execution_tenant_id):
            raise AuthorizationError(
                f"Cross-tenant execution cancellation denied for tenant '{identity.tenant_id}'. Admin or System role required.",
                details={
                    "caller_tenant": identity.tenant_id,
                    "target_tenant": execution_tenant_id,
                    "caller_role": identity.role.value,
                },
            )
