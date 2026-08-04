"""
Unit tests for PluginRecoveryEngine and RecoveryStrategy.
"""

from nexusai.plugins.contracts.state import PluginState
from nexusai.plugins.runtime.recovery import PluginRecoveryEngine, RecoveryStrategy
from nexusai.plugins.runtime.registry import PluginRegistry


def test_plugin_recovery_engine_thresholds():
    registry = PluginRegistry()
    engine = PluginRecoveryEngine(registry, max_failures=3)

    plugin_id = "failing.plugin"

    # First failure -> RETRY
    strat1 = engine.record_failure(plugin_id, "Error 1")
    assert strat1 == RecoveryStrategy.RETRY

    # Second failure -> BACKOFF
    strat2 = engine.record_failure(plugin_id, "Error 2")
    assert strat2 == RecoveryStrategy.BACKOFF

    # Third failure -> QUARANTINE
    strat3 = engine.record_failure(plugin_id, "Error 3")
    assert strat3 == RecoveryStrategy.QUARANTINE
    assert engine.is_quarantined(plugin_id) is True

    # Clear quarantine
    engine.clear_quarantine(plugin_id)
    assert engine.is_quarantined(plugin_id) is False
