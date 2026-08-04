"""
Unit tests for EventBus replay engine.
"""

import pytest
from nexusai.bus.bus import EventBus
from nexusai.plugins.events.events import PluginDiscoveredEvent


@pytest.mark.asyncio
async def test_event_bus_recording_and_replay():
    event_bus = EventBus(enable_replay=True)
    received: list[PluginDiscoveredEvent] = []

    async def subscriber(evt: PluginDiscoveredEvent) -> None:
        received.append(evt)

    # Publish events before subscription
    await event_bus.publish(PluginDiscoveredEvent(plugin_id="plugin.1", location="/p1"))
    await event_bus.publish(PluginDiscoveredEvent(plugin_id="plugin.2", location="/p2"))

    assert len(received) == 0

    # Subscribe and replay
    event_bus.subscribe(PluginDiscoveredEvent, subscriber)
    await event_bus.replay()

    assert len(received) == 2
    assert received[0].plugin_id == "plugin.1"
    assert received[1].plugin_id == "plugin.2"
