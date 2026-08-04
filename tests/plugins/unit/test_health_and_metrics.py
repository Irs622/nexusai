"""
Unit tests for PluginHealth reports and MetricsInterface telemetry.
"""

from nexusai.plugins.contracts.health import HealthStatus, PluginHealth
from nexusai.plugins.telemetry.metrics import MetricsInterface


def test_plugin_health_contract():
    h_ready = PluginHealth.ready("All systems operational", latency_ms=12)
    assert h_ready.status == HealthStatus.READY
    assert h_ready.diagnostics["latency_ms"] == 12

    h_degraded = PluginHealth.degraded("High memory usage")
    assert h_degraded.status == HealthStatus.DEGRADED


def test_metrics_interface_collection():
    metrics = MetricsInterface()
    metrics.counter("requests.total", 1.0, provider="openrouter")
    metrics.gauge("memory.used_mb", 128.5)
    metrics.timer("llm.latency", 0.45)

    records = metrics.get_records()
    assert len(records) == 3
    assert records[0].kind == "counter"
    assert records[1].kind == "gauge"
    assert records[2].kind == "timer"
