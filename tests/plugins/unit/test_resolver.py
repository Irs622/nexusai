"""
Unit tests for DependencyResolver and LoadingPlan calculation.
"""

import pytest

from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.exceptions import PluginDependencyError
from nexusai.plugins.runtime.resolver import DependencyResolver


def test_dependency_resolver_topological_sort():
    resolver = DependencyResolver()

    # B has no deps, A depends on B, C depends on A
    plugin_b = PluginManifest(id="plugin_b", name="B", version="1.0.0", entrypoint="mod:Class")
    plugin_a = PluginManifest(
        id="plugin_a", name="A", version="1.0.0", entrypoint="mod:Class", dependencies=["plugin_b"]
    )
    plugin_c = PluginManifest(
        id="plugin_c", name="C", version="1.0.0", entrypoint="mod:Class", dependencies=["plugin_a"]
    )

    plan = resolver.compute_loading_plan([plugin_c, plugin_a, plugin_b])
    assert plan.is_valid is True
    assert plan.order == ("plugin_b", "plugin_a", "plugin_c")


def test_dependency_resolver_missing_dependency():
    resolver = DependencyResolver()
    plugin_a = PluginManifest(
        id="plugin_a", name="A", version="1.0.0", entrypoint="mod:Class", dependencies=["missing_b"]
    )

    with pytest.raises(PluginDependencyError):
        resolver.compute_loading_plan([plugin_a])


def test_dependency_resolver_circular_dependency():
    resolver = DependencyResolver()
    plugin_a = PluginManifest(
        id="plugin_a", name="A", version="1.0.0", entrypoint="mod:Class", dependencies=["plugin_b"]
    )
    plugin_b = PluginManifest(
        id="plugin_b", name="B", version="1.0.0", entrypoint="mod:Class", dependencies=["plugin_a"]
    )

    with pytest.raises(PluginDependencyError):
        resolver.compute_loading_plan([plugin_a, plugin_b])
