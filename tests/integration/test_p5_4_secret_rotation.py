"""Dynamic credential rotation integration test suite for P5-4."""

from __future__ import annotations

import asyncio
import pytest

from nexusai.brain.domain.credential import CredentialReference
from nexusai.infrastructure.secrets.vault_credential_provider import VaultCredentialProvider


@pytest.mark.asyncio
async def test_dynamic_credential_rotation_without_restart() -> None:
    """Integration Test: Worker A resolves v1 secret -> Vault rotates to v2 -> Worker B resolves v2 secret without restart."""
    vault = VaultCredentialProvider()
    ref_v1 = CredentialReference("aws-secret-key", "process_tool", "production", "v1")

    # Worker A resolves v1
    res_a = await vault.resolve_credential(ref_v1)
    assert res_a.reference.version == "v1"

    # Vault performs dynamic secret rotation
    ref_v2 = await vault.rotate_credential(ref_v1, "rotated-aws-secret-v2-value")
    assert ref_v2.version == "v2"

    # Worker B resolves v2
    res_b = await vault.resolve_credential(ref_v2)
    assert res_b.reference.version == "v2"
    assert res_b.secret_value == "rotated-aws-secret-v2-value"
    assert res_b.secret_value != res_a.secret_value


if __name__ == "__main__":
    asyncio.run(test_dynamic_credential_rotation_without_restart())
    print("ALL DYNAMIC CREDENTIAL ROTATION INTEGRATION TESTS PASSED SUCCESSFULLY!")
