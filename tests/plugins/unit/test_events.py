"""
Unit tests for domain lifecycle events.
"""

from nexusai.plugins.contracts.state import PluginState
from nexusai.plugins.events.events import (
    CapabilityRegisteredEvent,
    PluginDiscoveredEvent,
    PluginFailedEvent,
    PluginLoadedEvent,
    PluginStartedEvent,
)


def test_domain_events_tracing_fields():
    event = PluginDiscoveredEvent(
        plugin_id="plugin.a",
        location="/tmp/path",
        manifest_format="yaml",
    )
    assert event.plugin_id == "plugin.a"
    assert event.event_id is not None
    assert event.timestamp > 0


def test_plugin_failed_event():
    event = PluginFailedEvent(
        plugin_id="plugin.err",
        error="Import error",
        failed_state=PluginState.FAILED,
    )
    assert event.failed_state == PluginState.FAILED
    assert event.error == "Import error"
