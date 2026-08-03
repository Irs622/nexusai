"""Provider Profile aggregating static metadata and dynamic runtime metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math

from nexusai.core.annotations import stable
from nexusai.logging.logger import logger
from nexusai.providers.metrics import ProviderRuntimeMetrics
from nexusai.providers.models import ProviderMetadata


@stable
@dataclass
class ProviderProfile:
    """Composite provider profile containing static metadata and dynamic runtime metrics."""

    metadata: ProviderMetadata
    metrics: ProviderRuntimeMetrics = field(default_factory=ProviderRuntimeMetrics)

    @property
    def provider_id(self) -> str:
        return self.metadata.provider_id

    @property
    def metrics_confidence(self) -> float:
        """Calculate multi-factor confidence score (0.0 to 1.0) evaluating sample size, variance stability, and recency.

        Returns:
            Float confidence score between 0.0 (unstable/no samples) and 1.0 (stable, low-variance, recent data).
        """
        latencies = self.metrics.rolling_latencies
        sample_count = len(latencies)
        if sample_count == 0:
            return 0.0

        # 1. Sample Size Score (0.0 to 1.0)
        sample_score = min(1.0, sample_count / 50.0)

        # 2. Variance Stability Score (1.0 = zero variance, lower for erratic spikes)
        mean_lat = sum(latencies) / sample_count
        if mean_lat > 0 and sample_count > 1:
            variance = sum((x - mean_lat) ** 2 for x in latencies) / sample_count
            std_dev = math.sqrt(variance)
            cv = std_dev / mean_lat  # coefficient of variation
            variance_score = max(0.1, 1.0 / (1.0 + cv))
        else:
            variance_score = 1.0

        # 3. Recency Score (decay over time since last check)
        now_ts = datetime.now(timezone.utc).timestamp()
        last_ts = self.metrics.last_checked_at.timestamp()
        elapsed_minutes = max(0.0, (now_ts - last_ts) / 60.0)
        recency_score = max(0.1, 1.0 / (1.0 + (elapsed_minutes / 30.0)))

        return sample_score * variance_score * recency_score


@stable
class ProviderProfileCache:
    """Cache store for ProviderProfile instances."""

    def __init__(self) -> None:
        self._profiles: dict[str, ProviderProfile] = {}

    def set(self, profile: ProviderProfile) -> None:
        self._profiles[profile.provider_id] = profile
        logger.info("Updated ProviderProfile cache for '{}'", profile.provider_id)

    def get(self, provider_id: str) -> ProviderProfile | None:
        return self._profiles.get(provider_id)

    def list_profiles(self) -> list[ProviderProfile]:
        return list(self._profiles.values())

    def clear(self) -> None:
        self._profiles.clear()
        logger.info("Cleared ProviderProfile cache")
