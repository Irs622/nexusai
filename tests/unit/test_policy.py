"""Unit tests for PluginPolicyEngine capability enforcement."""
import pytest
from nexusai.tools.plugin_manifest import PluginManifest, PluginCapabilities
from nexusai.security.policy import PluginPolicyEngine
from nexusai.core.errors import SecurityError
from nexusai.logging.context import CorrelationContext

def test_policy_engine_allows_permitted_capabilities() -> None:
    allowed = PluginCapabilities(read_filesystem=True, write_filesystem=True)
    engine = PluginPolicyEngine(allowed)
    
    manifest = PluginManifest(
        name="test_plugin",
        version="0.1.0",
        entrypoint="test_plugin:Plugin",
        capabilities=PluginCapabilities(read_filesystem=True)
    )
    # Should not raise exception
    engine.validate_capabilities(manifest)

def test_policy_engine_blocks_unauthorized_capability() -> None:
    allowed = PluginCapabilities(read_filesystem=True, terminal_execution=False)
    engine = PluginPolicyEngine(allowed)
    
    manifest = PluginManifest(
        name="dangerous_plugin",
        version="0.1.0",
        entrypoint="dangerous_plugin:Plugin",
        capabilities=PluginCapabilities(terminal_execution=True)
    )
    with pytest.raises(SecurityError):
        engine.validate_capabilities(manifest)

def test_correlation_context_async_safety() -> None:
    CorrelationContext.set_context(correlation_id="trace-12345", workflow_id="flow-999")
    ctx_dict = CorrelationContext.to_dict()
    assert ctx_dict["correlation_id"] == "trace-12345"
    assert ctx_dict["workflow_id"] == "flow-999"
