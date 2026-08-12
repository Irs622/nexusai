"""Protocol port interface for dynamic external credential resolution."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from nexusai.brain.domain.credential import CredentialReference, ResolvedCredential


@runtime_checkable
class ICredentialProvider(Protocol):
    """Protocol port interface for dynamic secret manager integration (Vault / Cloud KMS)."""

    async def resolve_credential(self, ref: CredentialReference) -> ResolvedCredential:
        """Dynamically resolve secret material into volatile memory for execution."""
        ...

    async def rotate_credential(self, ref: CredentialReference, new_secret_value: str) -> CredentialReference:
        """Rotate secret in provider without restarting application."""
        ...

    async def revoke_credential(self, ref: CredentialReference) -> bool:
        """Revoke secret in external secret manager."""
        ...
