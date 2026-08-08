"""
Unit tests for CQRS CommandBus, QueryBus, and EventBus.
"""

import pytest
from pydantic import BaseModel

from nexusai.bus.bus import CommandBus, EventBus, QueryBus
from nexusai.core.errors import CommandExecutionError


class SampleCommand(BaseModel):
    data: str


class SampleQuery(BaseModel):
    query_id: int


class SampleEvent(BaseModel):
    event_name: str


@pytest.mark.asyncio
async def test_command_bus_dispatch(command_bus: CommandBus) -> None:
    async def handler(cmd: SampleCommand) -> str:
        return f"Handled: {cmd.data}"

    command_bus.register(SampleCommand, handler)
    result = await command_bus.dispatch(SampleCommand(data="test_input"))
    assert result == "Handled: test_input"


@pytest.mark.asyncio
async def test_command_bus_unregistered(command_bus: CommandBus) -> None:
    with pytest.raises(CommandExecutionError):
        await command_bus.dispatch(SampleCommand(data="unregistered"))


@pytest.mark.asyncio
async def test_query_bus_execute(query_bus: QueryBus) -> None:
    async def handler(q: SampleQuery) -> dict[str, int]:
        return {"result": q.query_id * 2}

    query_bus.register(SampleQuery, handler)
    result = await query_bus.execute(SampleQuery(query_id=5))
    assert result == {"result": 10}


@pytest.mark.asyncio
async def test_event_bus_pub_sub(event_bus: EventBus) -> None:
    received_events: list[str] = []

    async def subscriber_one(evt: SampleEvent) -> None:
        received_events.append(f"sub1:{evt.event_name}")

    async def subscriber_two(evt: SampleEvent) -> None:
        received_events.append(f"sub2:{evt.event_name}")

    event_bus.subscribe(SampleEvent, subscriber_one)
    event_bus.subscribe(SampleEvent, subscriber_two)

    await event_bus.publish(SampleEvent(event_name="UserLoggedIn"))

    assert "sub1:UserLoggedIn" in received_events
    assert "sub2:UserLoggedIn" in received_events
