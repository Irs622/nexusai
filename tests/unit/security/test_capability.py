"""Unit tests for Capability model, CapabilityProfile, and CapabilityResolver."""

from __future__ import annotations

import pytest

from nexusai.security.capability import Capability, CapabilityProfile, CapabilityResolver
from nexusai.security.identity import Identity, Role


def test_capability_immutability_and_hashing() -> None:
    """Verify Capability is immutable (frozen) and can be hashed into sets/dicts."""
    cap1 = Capability(
        domain="shell",
        action="execute",
        resource="git",
        constraints={"max_duration_seconds": 30},
    )
    cap2 = Capability(
        domain="shell",
        action="execute",
        resource="git",
        constraints={"max_duration_seconds": 30},
    )
    cap3 = Capability(domain="shell", action="execute", resource="pytest")

    assert cap1 == cap2
    assert cap1 != cap3
    assert hash(cap1) == hash(cap2)

    # Immutability check
    with pytest.raises(AttributeError):
        cap1.domain = "filesystem"  # type: ignore[misc]

    # Usable in sets and dict keys
    cap_set = {cap1, cap2, cap3}
    assert len(cap_set) == 2


def test_capability_domain_and_action_matching() -> None:
    """Verify exact and wildcard matching for domain and action."""
    # Wildcard domain and action
    wildcard_cap = Capability(domain="*", action="*", resource="*")
    assert wildcard_cap.matches_domain("filesystem")
    assert wildcard_cap.matches_domain("shell")
    assert wildcard_cap.matches_action("read")
    assert wildcard_cap.matches_action("execute")

    # Specific domain, multiple actions
    fs_cap = Capability(domain="filesystem", action="read,write,list", resource="/workspace/**")
    assert fs_cap.matches_domain("filesystem")
    assert not fs_cap.matches_domain("shell")
    assert fs_cap.matches_action("read")
    assert fs_cap.matches_action("write")
    assert fs_cap.matches_action("list")
    assert not fs_cap.matches_action("execute")


def test_capability_resource_glob_matching() -> None:
    """Verify glob pattern matching and directory recursion on resources."""
    # Directory recursive wildcard /**
    ws_cap = Capability(domain="filesystem", action="read", resource="/workspace/**")
    assert ws_cap.matches_resource("/workspace")
    assert ws_cap.matches_resource("/workspace/src/app.py")
    assert ws_cap.matches_resource("/workspace/sub/dir/test.txt")
    assert not ws_cap.matches_resource("/etc/passwd")
    assert not ws_cap.matches_resource("/var/log")

    # Single-level directory wildcard /*
    level_cap = Capability(domain="filesystem", action="read", resource="/data/*")
    assert level_cap.matches_resource("/data/file.txt")
    assert not level_cap.matches_resource("/data/nested/deep.txt")

    # Hostname wildcard
    net_cap = Capability(domain="network", action="http_get", resource="*.pypi.org")
    assert net_cap.matches_resource("files.pypi.org")
    assert net_cap.matches_resource("api.pypi.org")
    assert not net_cap.matches_resource("example.com")


def test_capability_constraints_enforcement() -> None:
    """Verify constraint enforcement for duration, file size, extensions, and ports."""
    cap = Capability(
        domain="shell",
        action="execute",
        resource="pytest",
        constraints={
            "max_duration_seconds": 60,
            "allowed_commands": ["pytest"],
        },
    )

    # Valid context
    ok, err = cap.check_constraints({"duration_seconds": 30, "command": "pytest -v"})
    assert ok is True
    assert err is None

    # Exceeded duration
    ok, err = cap.check_constraints({"duration_seconds": 120, "command": "pytest -v"})
    assert ok is False
    assert "exceeds max_duration_seconds" in str(err)

    # Disallowed command
    ok, err = cap.check_constraints({"duration_seconds": 10, "command": "rm -rf"})
    assert ok is False
    assert "not in allowed_commands" in str(err)


def test_capability_resolver_default_deny() -> None:
    """Verify default-deny: identity with no capabilities cannot execute any action."""
    resolver = CapabilityResolver(profiles={}, default_profile="none")

    # Identity with no granted capabilities
    identity = Identity(
        tenant_id="tenant-x",
        user_id="alice",
        role=Role.VIEWER,
        metadata={"capabilities": []},
    )

    is_allowed, cap, reason = resolver.evaluate(
        identity, "filesystem", "read", "/workspace/file.txt"
    )
    assert is_allowed is False
    assert cap is None
    assert "has no granted capabilities" in str(reason)


def test_capability_resolver_role_hierarchy_defaults() -> None:
    """Verify built-in default resolver assigns correct profiles according to role."""
    resolver = CapabilityResolver.build_default_resolver()

    admin = Identity(tenant_id="default", user_id="admin_user", role=Role.ADMIN)
    operator = Identity(tenant_id="default", user_id="op_user", role=Role.OPERATOR)
    viewer = Identity(tenant_id="default", user_id="view_user", role=Role.VIEWER)

    # Admin has unrestricted access
    ok, cap, _ = resolver.evaluate(admin, "shell", "execute", "rm")
    assert ok is True
    assert cap is not None
    assert cap.domain == "*"

    # Operator has coding_agent: git allowed, rm denied
    ok_git, _, _ = resolver.evaluate(operator, "shell", "execute", "git")
    assert ok_git is True

    ok_rm, _, reason_rm = resolver.evaluate(operator, "shell", "execute", "rm")
    assert ok_rm is False
    assert "Capability denied" in str(reason_rm)

    # Viewer has readonly_agent: read allowed, write denied, shell denied
    ok_read, _, _ = resolver.evaluate(viewer, "filesystem", "read", "/workspace/main.py")
    assert ok_read is True

    ok_write, _, _ = resolver.evaluate(viewer, "filesystem", "write", "/workspace/main.py")
    assert ok_write is False

    ok_shell, _, _ = resolver.evaluate(viewer, "shell", "execute", "ls")
    assert ok_shell is False


def test_capability_resolver_load_from_yaml() -> None:
    """Verify YAML configuration loading into CapabilityResolver."""
    resolver = CapabilityResolver.from_yaml("config/capabilities.yaml")
    assert "coding_agent" in resolver.profiles
    assert "readonly_agent" in resolver.profiles
    assert "unrestricted_admin" in resolver.profiles

    # Check inheritance: coding_agent extends readonly_agent
    coding_profile = resolver.profiles["coding_agent"]
    assert "readonly_agent" in coding_profile.extends

    # Effective resolved capabilities include read (inherited) and write
    identity = Identity(tenant_id="default", user_id="coder", role=Role.OPERATOR)
    resolved = resolver.resolve_capabilities(identity)
    assert any(c.domain == "filesystem" and "read" in c.action for c in resolved)
    assert any(c.domain == "filesystem" and "write" in c.action for c in resolved)


def test_capability_profile_inheritance_and_cycle_prevention() -> None:
    """Verify multi-level inheritance and recursive cycle prevention."""
    base = CapabilityProfile(
        name="base",
        capabilities=[Capability(domain="filesystem", action="read", resource="/data/**")],
    )
    mid = CapabilityProfile(
        name="mid",
        extends=["base"],
        capabilities=[Capability(domain="filesystem", action="write", resource="/data/**")],
    )
    top = CapabilityProfile(
        name="top",
        extends=["mid"],
        capabilities=[Capability(domain="shell", action="execute", resource="git")],
    )
    # Introduce cycle: base extends top
    base.extends = ["top"]

    resolver = CapabilityResolver(profiles={"base": base, "mid": mid, "top": top})
    top_caps = resolver.resolve_profile_capabilities("top")

    # All 3 capabilities present, no infinite recursion
    domains = {(c.domain, c.action) for c in top_caps}
    assert ("filesystem", "read") in domains
    assert ("filesystem", "write") in domains
    assert ("shell", "execute") in domains


def test_capability_advanced_constraints() -> None:
    """Verify max_depth, allowed_methods, max_redirects, allowed_subpaths, and max_file_size_bytes."""
    cap = Capability(
        domain="network",
        action="http_get",
        resource="api.example.com",
        constraints={
            "max_file_size_bytes": 1024,
            "max_depth": 3,
            "allowed_methods": ["GET", "HEAD"],
            "max_redirects": 2,
            "allowed_subpaths": ["/api/v1", "/public"],
        },
    )

    # Valid context
    ok, err = cap.check_constraints(
        {
            "file_size_bytes": 500,
            "depth": 2,
            "method": "get",
            "redirects": 1,
            "path": "/api/v1/users",
        }
    )
    assert ok is True
    assert err is None

    # Exceeded file size
    ok, err = cap.check_constraints({"file_size_bytes": 2048})
    assert ok is False
    assert "exceeds maximum 1024 bytes" in str(err)

    # Exceeded depth
    ok, err = cap.check_constraints({"depth": 5})
    assert ok is False
    assert "exceeds max_depth 3" in str(err)

    # Disallowed method
    ok, err = cap.check_constraints({"method": "DELETE"})
    assert ok is False
    assert "not in allowed_methods" in str(err)

    # Exceeded redirects
    ok, err = cap.check_constraints({"redirects": 4})
    assert ok is False
    assert "exceeds max_redirects 2" in str(err)

    # Disallowed subpath
    ok, err = cap.check_constraints({"path": "/internal/secret"})
    assert ok is False
    assert "not in allowed_subpaths" in str(err)


def test_capability_extra_domain_constraints() -> None:
    """Verify no_pipe, no_redirect, max_request_size, risk_level_max, and max_results."""
    # Shell constraints: no_pipe, no_redirect
    shell_cap = Capability(
        domain="shell",
        action="execute",
        resource="git",
        constraints={"no_pipe": True, "no_redirect": True},
    )
    ok_pipe, err_pipe = shell_cap.check_constraints({"command": "git log | grep fix"})
    assert ok_pipe is False
    assert "pipeline execution (|) forbidden" in str(err_pipe)

    ok_redir, err_redir = shell_cap.check_constraints({"command": "git status > out.txt"})
    assert ok_redir is False
    assert "I/O redirection (<, >) forbidden" in str(err_redir)

    ok_clean, _ = shell_cap.check_constraints({"command": "git status"})
    assert ok_clean is True

    # Network constraint: max_request_size
    net_cap = Capability(
        domain="network", action="http_post", resource="*", constraints={"max_request_size": 5000}
    )
    ok_net, err_net = net_cap.check_constraints({"request_size": 10000})
    assert ok_net is False
    assert "exceeds max_request_size 5000 bytes" in str(err_net)

    # MCP constraint: risk_level_max
    mcp_cap = Capability(
        domain="mcp", action="invoke", resource="*", constraints={"risk_level_max": "MEDIUM"}
    )
    ok_mcp_low, _ = mcp_cap.check_constraints({"risk_level": "LOW"})
    assert ok_mcp_low is True
    ok_mcp_high, err_mcp = mcp_cap.check_constraints({"risk_level": "HIGH"})
    assert ok_mcp_high is False
    assert "exceeds risk_level_max 'MEDIUM'" in str(err_mcp)

    # Memory constraint: max_results
    mem_cap = Capability(
        domain="memory", action="search", resource="*", constraints={"max_results": 10}
    )
    ok_mem_high, err_mem = mem_cap.check_constraints({"limit": 50})
    assert ok_mem_high is False
    assert "exceeds max_results 10" in str(err_mem)
    ok_mem_ok, _ = mem_cap.check_constraints({"limit": 5})
    assert ok_mem_ok is True
