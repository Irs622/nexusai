"""
PluginSandbox Façade and resource access adapters.
"""

from __future__ import annotations

from typing import Any

from nexusai.plugins.security.permissions import PermissionEnforcer


class FilesystemAdapter:
    """Sandboxed filesystem access adapter."""

    def __init__(self, enforcer: PermissionEnforcer) -> None:
        self._enforcer = enforcer

    def read_text(self, path: str) -> str:
        """Read text from path after permission check."""
        self._enforcer.check_filesystem_read(path)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def write_text(self, path: str, content: str) -> None:
        """Write text to path after permission check."""
        self._enforcer.check_filesystem_write(path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


class NetworkAdapter:
    """Sandboxed network access adapter."""

    def __init__(self, enforcer: PermissionEnforcer) -> None:
        self._enforcer = enforcer

    def fetch(self, host: str, endpoint: str) -> dict[str, Any]:
        """Perform simulated/sandboxed network fetch after permission check."""
        self._enforcer.check_network_host(host)
        return {"status": "ok", "host": host, "endpoint": endpoint}


class PluginSandbox:
    """PluginSandbox façade exposing controlled resource adapters to plugins."""

    def __init__(self, enforcer: PermissionEnforcer) -> None:
        self._enforcer = enforcer
        self._filesystem = FilesystemAdapter(enforcer)
        self._network = NetworkAdapter(enforcer)

    @property
    def filesystem(self) -> FilesystemAdapter:
        """Return filesystem adapter."""
        return self._filesystem

    @property
    def network(self) -> NetworkAdapter:
        """Return network adapter."""
        return self._network

    @property
    def enforcer(self) -> PermissionEnforcer:
        """Return permission enforcer."""
        return self._enforcer
