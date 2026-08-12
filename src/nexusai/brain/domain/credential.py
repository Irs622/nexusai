"""Domain models for dynamic secret resolution and credential metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any


@dataclass(frozen=True)
class CredentialReference:
    """Immutable reference pointer to an external secret in Vault or KMS."""

    credential_ref: str
    tool_id: str
    environment: str = "production"
    version: str = "v1"


@dataclass(frozen=True)
class CredentialMetadata:
    """Non-sensitive metadata describing a resolved credential (persisted in audit logs)."""

    credential_ref: str
    credential_version: str
    credential_provider: str
    credential_resolved: bool = True
    resolved_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "credential_ref": self.credential_ref,
            "credential_version": self.credential_version,
            "credential_provider": self.credential_provider,
            "credential_resolved": self.credential_resolved,
            "resolved_at": self.resolved_at,
        }


@dataclass
class ResolvedCredential:
    """Transient container holding secret material strictly at execution boundary in volatile memory."""

    reference: CredentialReference
    secret_value: str
    provider_type: str
    expires_at: float = 0.0

    @property
    def is_expired(self) -> bool:
        if self.expires_at == 0.0:
            return False
        return time.time() >= self.expires_at

    def get_metadata(self) -> CredentialMetadata:
        return CredentialMetadata(
            credential_ref=self.reference.credential_ref,
            credential_version=self.reference.version,
            credential_provider=self.provider_type,
            credential_resolved=True,
        )
