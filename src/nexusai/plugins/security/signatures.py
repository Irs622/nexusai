"""
Plugin signature and checksum verifier for manifest integrity.
"""

from __future__ import annotations

import hashlib

from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.exceptions import PluginSignatureError


class PluginSignatureVerifier:
    """Verifies SHA256 checksums and author signature hashes for marketplace readiness."""

    @staticmethod
    def calculate_manifest_checksum(raw_content: str | bytes) -> str:
        """Calculate SHA256 digest string of manifest content."""
        if isinstance(raw_content, str):
            raw_content = raw_content.encode("utf-8")
        return hashlib.sha256(raw_content).hexdigest()

    def verify_manifest_hash(self, manifest: PluginManifest, raw_content: str | bytes) -> bool:
        """Verify that manifest.hash matches calculated digest if provided.

        Raises:
            PluginSignatureError: If hash mismatch occurs.
        """
        if not manifest.hash:
            return True

        calculated = self.calculate_manifest_checksum(raw_content)
        if calculated.lower() != manifest.hash.lower():
            raise PluginSignatureError(
                f"Manifest hash mismatch for plugin '{manifest.id}'. "
                f"Expected '{manifest.hash}', calculated '{calculated}'"
            )
        return True
