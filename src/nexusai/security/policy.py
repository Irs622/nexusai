"""Policy Engine for enforcing PluginManifest capabilities and permissions."""
from nexusai.tools.plugin_manifest import PluginManifest, PluginCapabilities
from nexusai.core.errors import SecurityError

class PluginPolicyEngine:
    """Enforces capability permissions requested in PluginManifest."""

    def __init__(self, allowed_capabilities: PluginCapabilities) -> None:
        self.allowed = allowed_capabilities

    def validate_capabilities(self, manifest: PluginManifest) -> None:
        """Validate requested capabilities against allowed security policy."""
        req = manifest.capabilities
        
        if req.terminal_execution and not self.allowed.terminal_execution:
            raise SecurityError(
                f"Security Policy Violation: Plugin '{manifest.name}' requested terminal_execution capability which is disabled by policy."
            )
        if req.write_filesystem and not self.allowed.write_filesystem:
            raise SecurityError(
                f"Security Policy Violation: Plugin '{manifest.name}' requested write_filesystem capability which is disabled by policy."
            )
        if req.applescript and not self.allowed.applescript:
            raise SecurityError(
                f"Security Policy Violation: Plugin '{manifest.name}' requested applescript capability which is disabled by policy."
            )
