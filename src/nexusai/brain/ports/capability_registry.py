"""ToolCapabilityRegistry for dynamic capability-to-provider tool mapping."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityProvider:
    """Tool provider implementation satisfying a target capability.

    Attributes:
        provider_name: Implementation provider name (e.g. "PyPDF", "Cloud OCR").
        tool_name: Registered tool name string.
        quality_score: Capability quality score (0.0 to 1.0).
        estimated_latency_ms: Mean estimated execution latency in ms.
        estimated_cost: Mean estimated execution cost.
    """

    provider_name: str
    tool_name: str
    quality_score: float = 0.9
    estimated_latency_ms: float = 10.0
    estimated_cost: float = 0.01


class ToolCapabilityRegistry:
    """Dynamic capability registry mapping capabilities to competing tool provider implementations."""

    def __init__(self) -> None:
        self._registry: dict[str, list[CapabilityProvider]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default capability providers."""
        self.register_provider(
            "locate_file",
            CapabilityProvider(
                provider_name="LocalFsSearch",
                tool_name="locate_file",
                quality_score=0.95,
                estimated_latency_ms=2.0,
            ),
        )
        self.register_provider(
            "read_file",
            CapabilityProvider(
                provider_name="PyPDFParser",
                tool_name="read_file",
                quality_score=0.90,
                estimated_latency_ms=15.0,
            ),
        )
        self.register_provider(
            "read_file",
            CapabilityProvider(
                provider_name="CloudOCR",
                tool_name="cloud_ocr_read",
                quality_score=0.98,
                estimated_latency_ms=120.0,
                estimated_cost=0.05,
            ),
        )

    def register_provider(self, capability: str, provider: CapabilityProvider) -> None:
        """Register a CapabilityProvider for a target capability."""
        if capability not in self._registry:
            self._registry[capability] = []
        self._registry[capability].append(provider)

    def resolve_best_provider(
        self, capability: str, max_latency_ms: float = 100.0
    ) -> CapabilityProvider | None:
        """Resolve the highest-quality provider satisfying max_latency_ms constraints."""
        providers = self._registry.get(capability, [])
        valid = [p for p in providers if p.estimated_latency_ms <= max_latency_ms]
        if not valid:
            return providers[0] if providers else None

        valid.sort(key=lambda p: p.quality_score, reverse=True)
        return valid[0]
