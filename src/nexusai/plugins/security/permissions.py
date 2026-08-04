"""
Scoped permissions model and PermissionEnforcer for resource access control.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexusai.plugins.exceptions import PluginPermissionError


@dataclass(frozen=True)
class ScopedPermissions:
    """Container for scoped permission rules."""

    filesystem_read: tuple[str, ...] = field(default_factory=tuple)
    filesystem_write: tuple[str, ...] = field(default_factory=tuple)
    network_hosts: tuple[str, ...] = field(default_factory=tuple)
    shell_commands: tuple[str, ...] = field(default_factory=tuple)
    allow_microphone: bool = False
    allow_clipboard: bool = False
    allow_notifications: bool = False
    allow_automation: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScopedPermissions:
        """Parse raw manifest permissions dict into ScopedPermissions."""
        fs = data.get("filesystem", {})
        net = data.get("network", {})
        shell = data.get("shell", {})

        return cls(
            filesystem_read=tuple(fs.get("read", [])),
            filesystem_write=tuple(fs.get("write", [])),
            network_hosts=tuple(net.get("hosts", [])),
            shell_commands=tuple(shell.get("commands", [])),
            allow_microphone=bool(data.get("microphone", False)),
            allow_clipboard=bool(data.get("clipboard", False)),
            allow_notifications=bool(data.get("notifications", False)),
            allow_automation=bool(data.get("automation", False)),
        )


class PermissionEnforcer:
    """Enforces explicit permission grants for plugin operations."""

    def __init__(self, permissions: ScopedPermissions) -> None:
        self._permissions = permissions

    @property
    def permissions(self) -> ScopedPermissions:
        """Return active scoped permissions."""
        return self._permissions

    def check_filesystem_read(self, path: str) -> None:
        """Check if path read access is allowed."""
        if not self._permissions.filesystem_read:
            raise PluginPermissionError(f"Filesystem read permission denied for path: '{path}'")
        # Wildcard or prefix match
        if "*" not in self._permissions.filesystem_read and not any(
            path.startswith(p) for p in self._permissions.filesystem_read
        ):
            raise PluginPermissionError(f"Filesystem read permission denied for path: '{path}'")

    def check_filesystem_write(self, path: str) -> None:
        """Check if path write access is allowed."""
        if not self._permissions.filesystem_write:
            raise PluginPermissionError(f"Filesystem write permission denied for path: '{path}'")
        if "*" not in self._permissions.filesystem_write and not any(
            path.startswith(p) for p in self._permissions.filesystem_write
        ):
            raise PluginPermissionError(f"Filesystem write permission denied for path: '{path}'")

    def check_network_host(self, host: str) -> None:
        """Check if network host access is allowed."""
        if not self._permissions.network_hosts:
            raise PluginPermissionError(f"Network access denied for host: '{host}'")
        if "*" not in self._permissions.network_hosts and host not in self._permissions.network_hosts:
            raise PluginPermissionError(f"Network access denied for host: '{host}'")
