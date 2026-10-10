"""Unit tests for PluginLoader dynamic discovery."""

import pytest

from nexusai.plugins.runtime.loader import PluginLoader, PluginLoadError
from nexusai.tools.registry import ToolRegistry


def test_plugin_loader_discovers_plugin() -> None:
    registry = ToolRegistry()
    loader = PluginLoader(registry)

    # Load official calculator plugin dynamically
    discovered = loader.load_from_module_path("plugins.calculator.plugin")
    assert len(discovered) == 1
    assert registry.has_tool("calculator")
    assert registry.get("calculator").description == "Evaluate mathematical expression"


def test_plugin_loader_invalid_module_raises_error() -> None:
    registry = ToolRegistry()
    loader = PluginLoader(registry)

    with pytest.raises(PluginLoadError):
        loader.load_from_module_path("non_existent_module_xyz")


def test_single_canonical_plugin_loader() -> None:
    """AUDIT-21: exactly one PluginLoader class is defined in the source tree."""
    import pathlib
    import re

    src = pathlib.Path(__file__).resolve().parents[2] / "src" / "nexusai"
    definitions = [
        p
        for p in src.rglob("*.py")
        if re.search(r"^class PluginLoader\b", p.read_text(encoding="utf-8"), re.M)
    ]
    assert [p.relative_to(src).as_posix() for p in definitions] == ["plugins/runtime/loader.py"]


def test_deprecated_tools_alias_warns_and_returns_canonical_class() -> None:
    import pytest

    import nexusai.tools.plugin_loader as legacy
    from nexusai.plugins.runtime import loader as canonical

    with pytest.warns(DeprecationWarning, match="nexusai.plugins.runtime.loader"):
        assert legacy.PluginLoader is canonical.PluginLoader
    with pytest.warns(DeprecationWarning):
        assert legacy.PluginLoadError is canonical.PluginLoadError
