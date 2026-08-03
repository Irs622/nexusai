"""Unit tests for PluginLoader dynamic discovery."""
import pytest
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.plugin_loader import PluginLoader, PluginLoadError

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
