"""
Unit tests for nexusai create-tool and nexusai create-mcp CLI scaffolding commands.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexusai.cli.app import app
from nexusai.cli.scaffolding import (
    scaffold_mcp,
    scaffold_tool,
    _to_class_name,
    _validate_name,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Unit: internal helpers
# ---------------------------------------------------------------------------


class TestValidateName:
    """Tests for _validate_name() identifier guard."""

    def test_valid_simple(self) -> None:
        _validate_name("mytool")  # no error

    def test_valid_with_underscores(self) -> None:
        _validate_name("my_cool_tool")  # no error

    def test_valid_with_digits(self) -> None:
        _validate_name("tool2")  # no error

    def test_rejects_uppercase(self) -> None:
        with pytest.raises(ValueError, match="Invalid name"):
            _validate_name("MyTool")

    def test_rejects_leading_digit(self) -> None:
        with pytest.raises(ValueError, match="Invalid name"):
            _validate_name("2tool")

    def test_rejects_hyphen(self) -> None:
        with pytest.raises(ValueError, match="Invalid name"):
            _validate_name("my-tool")

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="Invalid name"):
            _validate_name("")

    def test_rejects_space(self) -> None:
        with pytest.raises(ValueError, match="Invalid name"):
            _validate_name("my tool")


class TestToClassName:
    """Tests for _to_class_name() converter."""

    def test_single_word(self) -> None:
        assert _to_class_name("tool") == "Tool"

    def test_two_words(self) -> None:
        assert _to_class_name("my_tool") == "MyTool"

    def test_three_words(self) -> None:
        assert _to_class_name("my_cool_tool") == "MyCoolTool"


# ---------------------------------------------------------------------------
# Unit: scaffold_tool()
# ---------------------------------------------------------------------------


class TestScaffoldTool:
    """Tests for scaffold_tool() engine."""

    def test_dry_run_produces_no_files(self, tmp_path: Path) -> None:
        result = scaffold_tool(
            name="alpha",
            description="Test alpha tool",
            output_dir=tmp_path / "plugins",
            dry_run=True,
        )
        assert result.dry_run is True
        assert not (tmp_path / "plugins" / "alpha").exists()

    def test_dry_run_still_reports_files(self, tmp_path: Path) -> None:
        result = scaffold_tool(
            name="alpha",
            description="Test alpha tool",
            output_dir=tmp_path / "plugins",
            dry_run=True,
        )
        assert len(result.files_written) == 4

    def test_writes_expected_files(self, tmp_path: Path) -> None:
        scaffold_tool(
            name="beta",
            description="Beta tool",
            output_dir=tmp_path / "plugins",
        )
        dest = tmp_path / "plugins" / "beta"
        assert (dest / "__init__.py").exists()
        assert (dest / "plugin.py").exists()
        assert (dest / "nexusai_manifest.yaml").exists()
        assert (dest / "README.md").exists()

    def test_plugin_py_contains_class_name(self, tmp_path: Path) -> None:
        scaffold_tool(
            name="my_tool",
            description="My tool",
            output_dir=tmp_path / "plugins",
        )
        content = (tmp_path / "plugins" / "my_tool" / "plugin.py").read_text()
        assert "class MyToolTool(BaseTool)" in content
        assert "class MyToolPlugin" in content

    def test_manifest_contains_name(self, tmp_path: Path) -> None:
        scaffold_tool(
            name="gamma",
            description="Gamma desc",
            output_dir=tmp_path / "plugins",
        )
        content = (tmp_path / "plugins" / "gamma" / "nexusai_manifest.yaml").read_text()
        assert "name: gamma" in content
        assert "entrypoint:" in content

    def test_overwrite_false_skips_existing(self, tmp_path: Path) -> None:
        out = tmp_path / "plugins"
        scaffold_tool(name="delta", description="D", output_dir=out)
        plugin_path = out / "delta" / "plugin.py"
        plugin_path.write_text("OVERRIDDEN")

        scaffold_tool(name="delta", description="D", output_dir=out, overwrite=False)
        assert plugin_path.read_text() == "OVERRIDDEN"

    def test_overwrite_true_replaces_existing(self, tmp_path: Path) -> None:
        out = tmp_path / "plugins"
        scaffold_tool(name="epsilon", description="E", output_dir=out)
        plugin_path = out / "epsilon" / "plugin.py"
        plugin_path.write_text("OVERRIDDEN")

        scaffold_tool(name="epsilon", description="E", output_dir=out, overwrite=True)
        assert "class EpsilonTool" in plugin_path.read_text()

    def test_invalid_name_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid name"):
            scaffold_tool(name="Bad-Name", description="x", output_dir=tmp_path)

    def test_result_contains_destination(self, tmp_path: Path) -> None:
        result = scaffold_tool(name="zeta", description="Z", output_dir=tmp_path / "plugins")
        assert result.destination == tmp_path / "plugins" / "zeta"


# ---------------------------------------------------------------------------
# Unit: scaffold_mcp()
# ---------------------------------------------------------------------------


class TestScaffoldMcp:
    """Tests for scaffold_mcp() engine."""

    def test_writes_expected_files(self, tmp_path: Path) -> None:
        scaffold_mcp(
            name="my_mcp",
            description="My MCP server",
            output_dir=tmp_path / "plugins" / "mcp",
        )
        dest = tmp_path / "plugins" / "mcp" / "my_mcp"
        assert (dest / "__init__.py").exists()
        assert (dest / "server.py").exists()
        assert (dest / "nexusai_mcp.yaml").exists()
        assert (dest / "README.md").exists()

    def test_server_py_contains_tool_entry(self, tmp_path: Path) -> None:
        scaffold_mcp(
            name="news",
            description="News MCP",
            output_dir=tmp_path / "mcp",
        )
        content = (tmp_path / "mcp" / "news" / "server.py").read_text()
        assert '"news_hello"' in content
        assert "asyncio.run(_main())" in content

    def test_config_yaml_contains_server_name(self, tmp_path: Path) -> None:
        scaffold_mcp(
            name="weather",
            description="Weather MCP",
            output_dir=tmp_path / "mcp",
        )
        content = (tmp_path / "mcp" / "weather" / "nexusai_mcp.yaml").read_text()
        assert "name: weather" in content
        assert "transport: stdio" in content

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        result = scaffold_mcp(
            name="phantom",
            description="Ghost MCP",
            output_dir=tmp_path / "mcp",
            dry_run=True,
        )
        assert result.dry_run is True
        assert not (tmp_path / "mcp" / "phantom").exists()
        assert len(result.files_written) == 4

    def test_invalid_name_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid name"):
            scaffold_mcp(name="My-MCP", description="x", output_dir=tmp_path)


# ---------------------------------------------------------------------------
# Integration: Typer CLI commands
# ---------------------------------------------------------------------------


class TestCreateToolCommand:
    """Tests for `nexusai create-tool` via Typer test runner."""

    def test_help_text(self) -> None:
        result = runner.invoke(app, ["create-tool", "--help"])
        assert result.exit_code == 0
        assert "Scaffold" in result.output

    def test_invalid_name_exits_nonzero(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["create-tool", "Bad-Name", "--output-dir", str(tmp_path)],
        )
        assert result.exit_code != 0

    def test_dry_run_flag(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "create-tool",
                "sample",
                "--output-dir",
                str(tmp_path),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "sample" in result.output
        assert not (tmp_path / "sample").exists()

    def test_creates_plugin_directory(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "create-tool",
                "mywidget",
                "--description",
                "Widget tool",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert (tmp_path / "mywidget" / "plugin.py").exists()
        assert "scaffolded successfully" in result.output


class TestCreateMcpCommand:
    """Tests for `nexusai create-mcp` via Typer test runner."""

    def test_help_text(self) -> None:
        result = runner.invoke(app, ["create-mcp", "--help"])
        assert result.exit_code == 0
        assert "Scaffold" in result.output

    def test_invalid_name_exits_nonzero(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["create-mcp", "Bad-MCP", "--output-dir", str(tmp_path)],
        )
        assert result.exit_code != 0

    def test_dry_run_flag(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "create-mcp",
                "testserver",
                "--output-dir",
                str(tmp_path),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "testserver" in result.output
        assert not (tmp_path / "testserver").exists()

    def test_creates_server_directory(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "create-mcp",
                "myserver",
                "--description",
                "My new MCP server",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert (tmp_path / "myserver" / "server.py").exists()
        assert "scaffolded successfully" in result.output
