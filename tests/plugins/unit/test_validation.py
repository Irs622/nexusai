"""
Unit tests for PluginValidator and APIVersionNegotiator.
"""

import pytest
from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.exceptions import PluginAPIVersionError, PluginValidationError
from nexusai.plugins.validation import APIVersionNegotiator, PluginValidator


def test_api_version_negotiator_success():
    negotiator = APIVersionNegotiator()
    manifest = PluginManifest(
        id="valid.plugin",
        name="Valid",
        version="1.0.0",
        entrypoint="mod:Class",
        plugin_api=1,
        minimum_kernel="0.1.0",
    )
    assert negotiator.evaluate_compatibility(manifest) is True


def test_api_version_negotiator_incompatible_api():
    negotiator = APIVersionNegotiator()
    manifest = PluginManifest(
        id="incompat.plugin",
        name="Incompat",
        version="1.0.0",
        entrypoint="mod:Class",
        plugin_api=99,
    )
    with pytest.raises(PluginAPIVersionError):
        negotiator.evaluate_compatibility(manifest)


def test_plugin_validator_invalid_id():
    validator = PluginValidator()
    manifest = PluginManifest(
        id="invalid id with spaces!",
        name="Invalid",
        version="1.0.0",
        entrypoint="mod:Class",
    )
    with pytest.raises(PluginValidationError):
        validator.validate_manifest(manifest)


def test_plugin_validator_invalid_entrypoint():
    validator = PluginValidator()
    manifest = PluginManifest(
        id="valid.id",
        name="Invalid Entry",
        version="1.0.0",
        entrypoint="no_colon_entrypoint",
    )
    with pytest.raises(PluginValidationError):
        validator.validate_manifest(manifest)
