"""
DependencyResolver for topological DAG sorting and LoadingPlan generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from nexusai.plugins.contracts.manifest import PluginManifest
from nexusai.plugins.exceptions import PluginDependencyError


@dataclass(frozen=True)
class LoadingPlan:
    """Structured resolution plan computed by DependencyResolver."""

    order: tuple[str, ...]
    missing_dependencies: tuple[str, ...] = field(default_factory=tuple)
    optional_dependencies: tuple[str, ...] = field(default_factory=tuple)
    cycles: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    disabled_plugins: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        """Return True if plan has no missing dependencies or cycles."""
        return len(self.missing_dependencies) == 0 and len(self.cycles) == 0


class DependencyResolver:
    """Computes DAG dependency resolution and loading order for plugins."""

    def compute_loading_plan(
        self,
        manifests: Sequence[PluginManifest],
        disabled_ids: set[str] | None = None,
    ) -> LoadingPlan:
        """Compute DAG topological sort loading plan.

        Raises:
            PluginDependencyError: If required dependencies are missing or circular.
        """
        disabled = disabled_ids or set()
        manifest_map: dict[str, PluginManifest] = {m.id: m for m in manifests}

        missing: list[str] = []
        optional_missing: list[str] = []

        # Validate dependency availability
        for m in manifests:
            if m.id in disabled:
                continue
            for dep in m.dependencies:
                if dep not in manifest_map or dep in disabled:
                    missing.append(f"Plugin '{m.id}' requires missing dependency '{dep}'")
            for opt in m.optional_dependencies:
                if opt not in manifest_map or opt in disabled:
                    optional_missing.append(opt)

        if missing:
            raise PluginDependencyError("; ".join(missing))

        # Build adjacency list (dep -> dependents) and in-degree map for active plugins
        active_ids = [m.id for m in manifests if m.id not in disabled]
        in_degree: dict[str, int] = {pid: 0 for pid in active_ids}
        adj: dict[str, list[str]] = {pid: [] for pid in active_ids}

        for pid in active_ids:
            m = manifest_map[pid]
            for dep in m.dependencies:
                if dep in manifest_map and dep not in disabled:
                    adj[dep].append(pid)
                    in_degree[pid] += 1

        # Kahn's algorithm for topological sorting
        queue = [pid for pid in active_ids if in_degree[pid] == 0]
        order: list[str] = []

        while queue:
            curr = queue.pop(0)
            order.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(active_ids):
            unresolved = set(active_ids) - set(order)
            raise PluginDependencyError(
                f"Circular dependency detected involving plugins: {sorted(unresolved)}"
            )

        return LoadingPlan(
            order=tuple(order),
            missing_dependencies=tuple(missing),
            optional_dependencies=tuple(optional_missing),
            disabled_plugins=tuple(sorted(disabled)),
        )
