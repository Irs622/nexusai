"""Reusable contract test suite for ICredentialProvider implementations (Vault and KMS)."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.credential import CredentialReference
from nexusai.brain.ports.credential_provider_port import ICredentialProvider
from nexusai.infrastructure.secrets.kms_credential_provider import KMSCredentialProvider
from nexusai.infrastructure.secrets.vault_credential_provider import VaultCredentialProvider


async def verify_credential_provider_contract(provider: ICredentialProvider) -> None:
    """Verify any ICredentialProvider adapter conforms to the domain contract."""
    ref = CredentialReference("openai-key", "process_tool", "production", "v1")

    # 1. Resolve credential into volatile memory
    resolved = await provider.resolve_credential(ref)
    assert resolved.reference == ref
    assert resolved.secret_value != ""
    assert resolved.is_expired is False

    # 2. Get non-sensitive metadata for audit persistence
    meta = resolved.get_metadata()
    assert meta.credential_ref == "openai-key"
    assert meta.credential_version == "v1"
    assert "secret_value" not in meta.to_dict()

    # 3. Rotate credential
    new_ref = await provider.rotate_credential(ref, "new-secret-val-v2")
    assert new_ref.version == "v2"

    # 4. Revoke credential
    revoked = await provider.revoke_credential(ref)
    assert isinstance(revoked, bool)


@pytest.mark.asyncio
async def test_vault_provider_conformance() -> None:
    """Test VaultCredentialProvider conformance to ICredentialProvider contract."""
    provider = VaultCredentialProvider()
    await verify_credential_provider_contract(provider)


@pytest.mark.asyncio
async def test_kms_provider_conformance() -> None:
    """Test KMSCredentialProvider conformance to ICredentialProvider contract."""
    provider = KMSCredentialProvider()
    await verify_credential_provider_contract(provider)


if __name__ == "__main__":
    asyncio.run(test_vault_provider_conformance())
    asyncio.run(test_kms_provider_conformance())
    print("ALL CREDENTIAL PROVIDER CONTRACT TESTS PASSED SUCCESSFULLY!")
