"""
Unit tests for EventBus subscriber filtering and interceptor pipeline.
"""

import pytest
from nexusai.bus.bus import EventBus
from nexusai.plugins.events.events import PluginStartedEvent


@pytest.mark.asyncio
async def test_event_bus_predicate_filtering():
    event_bus = EventBus(enable_replay=False)
    received: list[PluginStartedEvent] = []

    async def subscriber(evt: PluginStartedEvent) -> None:
        received.append(evt)

    # Filter: Only accept plugins starting with "target."
    def filter_fn(evt: PluginStartedEvent) -> bool:
        return evt.plugin_id.startswith("target.")

    event_bus.subscribe(PluginStartedEvent, subscriber, filter_fn=filter_fn)

    # Publish matching event
    await event_bus.publish(PluginStartedEvent(plugin_id="target.llm", capabilities=["llm.provider"]))
    # Publish non-matching event
    await event_bus.publish(PluginStartedEvent(plugin_id="other.tool", capabilities=["tool.integration"]))

    assert len(received) == 1
    assert received[0].plugin_id == "target.llm"


@pytest.mark.asyncio
async def test_event_bus_interceptor_pipeline():
    event_bus = EventBus(enable_replay=False)
    intercepted: list[str] = []

    async def interceptor(evt: object) -> None:
        intercepted.append(type(evt).__name__)

    event_bus.add_interceptor(interceptor)
    await event_bus.publish(PluginStartedEvent(plugin_id="plugin.a"))

    assert "PluginStartedEvent" in intercepted
