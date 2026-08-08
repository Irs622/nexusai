"""RuntimeCapabilityDiscovery and DynamicCapabilityGraphBuilder for dynamic capability graph construction."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from nexusai.brain.domain.agent import CapabilityGraph


@dataclass(frozen=True)
class CapabilityAdvertisement:
    """Dynamic capability advertisement published by active tool providers or MCP servers."""

    capability_name: str
    provider_name: str
    tool_name: str
    prerequisite_capabilities: tuple[str, ...] = ()
    quality_score: float = 0.9
    estimated_latency_ms: float = 10.0
    is_active: bool = True
    discovered_at: float = field(default_factory=time.time)


class RuntimeCapabilityDiscovery:
    """Discovers and maintains live active capability advertisements from runtime environment."""

    def __init__(self) -> None:
        self._advertisements: dict[str, CapabilityAdvertisement] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Seed default runtime capability advertisements."""
        self.publish_capability(
            CapabilityAdvertisement(
                capability_name="locate_file",
                provider_name="LocalFs",
                tool_name="locate_file",
                prerequisite_capabilities=(),
            )
        )
        self.publish_capability(
            CapabilityAdvertisement(
                capability_name="read_file",
                provider_name="PyPDFParser",
                tool_name="read_file",
                prerequisite_capabilities=("locate_file",),
            )
        )
        self.publish_capability(
            CapabilityAdvertisement(
                capability_name="summarize_file",
                provider_name="DefaultSummarizer",
                tool_name="summarize_file",
                prerequisite_capabilities=("read_file",),
            )
        )

    def publish_capability(self, advertisement: CapabilityAdvertisement) -> None:
        """Publish or update an active CapabilityAdvertisement."""
        self._advertisements[advertisement.capability_name] = advertisement

    def revoke_capability(self, capability_name: str) -> None:
        """Revoke an inactive capability (e.g. MCP server disconnected)."""
        if capability_name in self._advertisements:
            del self._advertisements[capability_name]

    def get_active_capabilities(self) -> list[CapabilityAdvertisement]:
        """Return list of all currently active CapabilityAdvertisements."""
        return [ad for ad in self._advertisements.values() if ad.is_active]


class DynamicCapabilityGraphBuilder:
    """Builds fresh, ephemeral CapabilityGraph instances on-the-fly from live RuntimeCapabilityDiscovery."""

    def build_graph(self, discovery: RuntimeCapabilityDiscovery) -> CapabilityGraph:
        """Construct a fresh runtime CapabilityGraph from active capability advertisements."""
        active_ads = discovery.get_active_capabilities()
        req_map: dict[str, tuple[str, ...]] = {}

        for ad in active_ads:
            req_map[ad.tool_name] = ad.prerequisite_capabilities

        return CapabilityGraph(requirements=req_map)
