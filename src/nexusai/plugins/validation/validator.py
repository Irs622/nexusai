"""
PluginValidator for schema integrity and capability verification.
"""

from __future__ import annotations

import re
from typing import Sequence

from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.exceptions import PluginValidationError
from nexusai.plugins.validation.api_version import APIVersionNegotiator


class PluginValidator:
    """Pre-flight validator for manifests and plugin candidates."""

    ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

    def __init__(self, api_negotiator: APIVersionNegotiator | None = None) -> None:
        self.api_negotiator = api_negotiator or APIVersionNegotiator()

    def validate_manifest(self, manifest: PluginManifest) -> None:
        """Perform comprehensive manifest validation.

        Raises:
            PluginValidationError: If any validation rule is violated.
        """
        # 1. Validate ID format
        if not manifest.id or not self.ID_PATTERN.match(manifest.id):
            raise PluginValidationError(f"Invalid plugin ID '{manifest.id}'. Must contain only alphanumeric, '-', '_', '.'")

        # 2. Validate entrypoint format (module.submodule:ClassName)
        if ":" not in manifest.entrypoint:
            raise PluginValidationError(
                f"Invalid entrypoint format '{manifest.entrypoint}' for plugin '{manifest.id}'. "
                "Expected format 'module.submodule:ClassName'"
            )

        # 3. Check API version compatibility
        self.api_negotiator.evaluate_compatibility(manifest)

    def check_duplicate_ids(self, manifests: Sequence[PluginManifest]) -> None:
        """Ensure no duplicate plugin IDs exist within a batch of manifests."""
        seen_ids: set[str] = set()
        for manifest in manifests:
            if manifest.id in seen_ids:
                raise PluginValidationError(f"Duplicate plugin ID '{manifest.id}' detected")
            seen_ids.add(manifest.id)
