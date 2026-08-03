"""Hello World example for NexusAI."""
import asyncio
from nexusai.bus.bus import EventBus
from nexusai.bus.events import BaseEvent

class HelloEvent(BaseEvent):
    message: str = "Hello NexusAI World!"

async def main() -> None:
    bus = EventBus()
    
    @bus.on(HelloEvent)
    async def handle_hello(event: HelloEvent) -> None:
        print(f"Received event: {event.message}")
        
    await bus.publish(HelloEvent())

if __name__ == "__main__":
    asyncio.run(main())
