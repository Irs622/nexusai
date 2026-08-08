"""
Unit tests for ScopedPermissions, PermissionEnforcer, and PluginSandbox.
"""

import pytest

from nexusai.plugins.exceptions import PluginPermissionError
from nexusai.plugins.runtime.sandbox import PluginSandbox
from nexusai.plugins.security import PermissionEnforcer, ScopedPermissions


def test_permission_enforcer_filesystem_allowed():
    perms = ScopedPermissions.from_dict(
        {"filesystem": {"read": ["/tmp/allowed"], "write": ["/tmp/allowed"]}}
    )
    enforcer = PermissionEnforcer(perms)

    enforcer.check_filesystem_read("/tmp/allowed/file.txt")
    enforcer.check_filesystem_write("/tmp/allowed/file.txt")


def test_permission_enforcer_filesystem_denied():
    perms = ScopedPermissions.from_dict({"filesystem": {"read": ["/tmp/allowed"]}})
    enforcer = PermissionEnforcer(perms)

    with pytest.raises(PluginPermissionError):
        enforcer.check_filesystem_read("/etc/passwd")

    with pytest.raises(PluginPermissionError):
        enforcer.check_filesystem_write("/tmp/allowed/file.txt")


def test_permission_enforcer_network():
    perms = ScopedPermissions.from_dict({"network": {"hosts": ["api.openai.com"]}})
    enforcer = PermissionEnforcer(perms)

    enforcer.check_network_host("api.openai.com")

    with pytest.raises(PluginPermissionError):
        enforcer.check_network_host("untrusted.site.com")


def test_plugin_sandbox_network_adapter():
    perms = ScopedPermissions.from_dict({"network": {"hosts": ["openrouter.ai"]}})
    sandbox = PluginSandbox(PermissionEnforcer(perms))

    res = sandbox.network.fetch("openrouter.ai", "/v1/chat")
    assert res["status"] == "ok"
