"""Hello World example for NexusAI."""
import asyncio
from nexusai.bus.bus import EventBus
from nexusai.bus.events import ToolExecutedEvent

async def main() -> None:
    bus = EventBus()
    
    async def handle_tool_executed(event: ToolExecutedEvent) -> None:
        print(f"Received event for tool: {event.tool_name}, success: {event.success}")
        
    bus.subscribe(ToolExecutedEvent, handle_tool_executed)
    await bus.publish(ToolExecutedEvent(tool_name="hello_tool", success=True))

if __name__ == "__main__":
    asyncio.run(main())
