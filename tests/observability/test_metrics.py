"""
Unit tests for TokenLatencyTracker and TelemetryCollector metrics.
"""

import time
from nexusai.observability.metrics import TelemetryCollector, TokenLatencyTracker


def test_token_latency_tracker_calculation():
    tracker = TokenLatencyTracker(provider="openrouter", model="anthropic/claude-3-5-sonnet")

    time.sleep(0.01)
    tracker.record_first_token()
    tracker.record_token()
    tracker.record_token()

    metric = tracker.finalize()
    assert metric.provider == "openrouter"
    assert metric.model == "anthropic/claude-3-5-sonnet"
    assert metric.time_to_first_token_ms > 0.0
    assert metric.token_count == 2
    assert metric.tokens_per_second > 0.0


def test_telemetry_collector_recording():
    collector = TelemetryCollector()
    tracker = TokenLatencyTracker(provider="gemini", model="gemini-1.5-pro")
    tracker.record_token()
    metric = tracker.finalize()

    collector.record_token_latency(metric)
    records = collector.get_token_latency_records()

    assert len(records) == 1
    assert records[0].provider == "gemini"
