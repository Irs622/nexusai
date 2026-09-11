"""Identity and Tenant Context models for NexusAI multi-tenant security architecture."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(str, Enum):
    """Hierarchical RBAC user roles."""

    VIEWER = "viewer"  # Read-only: status, audit, DAG plans
    OPERATOR = "operator"  # Execute LOW/MEDIUM risk tools, approve workflows
    ADMIN = "admin"  # Execute HIGH/CRITICAL tools, manage keys, configure runtime
    SYSTEM = "system"  # Internal service accounts, full access


ROLE_HIERARCHY: dict[Role, int] = {
    Role.VIEWER: 10,
    Role.OPERATOR: 20,
    Role.ADMIN: 30,
    Role.SYSTEM: 40,
}


@dataclass(frozen=True)
class Identity:
    """Authenticated caller identity contract transporting tenant, user, and role context."""

    tenant_id: str
    user_id: str
    role: Role
    api_key_id: str = ""
    scopes: frozenset[str] = field(default_factory=frozenset)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_at_least(self, target_role: Role) -> bool:
        """Check if identity role is greater than or equal to target role in hierarchy."""
        return ROLE_HIERARCHY.get(self.role, 0) >= ROLE_HIERARCHY.get(target_role, 0)


# ContextVar for thread-safe / coroutine-safe ambient tenant identity propagation
_CURRENT_IDENTITY: contextvars.ContextVar[Identity | None] = contextvars.ContextVar(
    "nexusai_current_identity", default=None
)


from nexusai.core.errors import AuthenticationError


class TenantContext:
    """Ambient tenant and identity context manager."""

    @staticmethod
    def get_current_identity() -> Identity | None:
        """Retrieve current authenticated identity from ambient context."""
        return _CURRENT_IDENTITY.get()

    @staticmethod
    def get() -> Identity | None:
        """Retrieve current authenticated identity from ambient context."""
        return _CURRENT_IDENTITY.get()

    @staticmethod
    def get_required() -> Identity:
        """Retrieve current authenticated identity, raising AuthenticationError if absent."""
        identity = _CURRENT_IDENTITY.get()
        if identity is None:
            raise AuthenticationError("No active tenant context")
        return identity

    @staticmethod
    def get_current_tenant() -> str:
        """Retrieve current tenant identifier from ambient context, defaulting to 'default'."""
        identity = _CURRENT_IDENTITY.get()
        if identity is not None and identity.tenant_id:
            return identity.tenant_id
        return "default"

    @staticmethod
    def set_current_identity(identity: Identity | None) -> contextvars.Token[Identity | None]:
        """Set ambient identity context, returning reset token."""
        return _CURRENT_IDENTITY.set(identity)

    @staticmethod
    def set(identity: Identity | None) -> contextvars.Token[Identity | None]:
        """Set ambient identity context, returning reset token."""
        return _CURRENT_IDENTITY.set(identity)

    @staticmethod
    def reset_current_identity(token: contextvars.Token[Identity | None]) -> None:
        """Reset ambient identity context using token."""
        _CURRENT_IDENTITY.reset(token)

    @staticmethod
    def reset(token: contextvars.Token[Identity | None]) -> None:
        """Reset ambient identity context using token."""
        _CURRENT_IDENTITY.reset(token)
