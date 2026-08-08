"""Event Bus Demo — NexusAI Pub-Sub Domain Events."""

from __future__ import annotations

import asyncio

from nexusai.brain.events.bus import (
    AgentEventBus,
    ExecutionFinishedEvent,
    PlannerFinishedEvent,
    ToolFailedEvent,
)


async def main() -> None:
    print("=== NexusAI AgentEventBus Pub-Sub Demo ===")

    bus = AgentEventBus()

    # Define event subscriber callbacks
    def on_planner_finished(event: PlannerFinishedEvent) -> None:
        print(
            f"  [Subscriber 1] Planner finished! Goal: '{event.goal_description}' | Steps: {event.step_count}"
        )

    async def on_execution_finished(event: ExecutionFinishedEvent) -> None:
        print(
            f"  [Subscriber 2] Async listener: Execution completed. Success={event.success} | Steps={event.executed_steps}"
        )

    def on_tool_failed(event: ToolFailedEvent) -> None:
        print(f"  [Subscriber 3] Alert! Tool '{event.tool_name}' failed: {event.error_message}")

    # Register subscribers
    bus.subscribe(PlannerFinishedEvent, on_planner_finished)
    bus.subscribe(ExecutionFinishedEvent, on_execution_finished)
    bus.subscribe(ToolFailedEvent, on_tool_failed)

    print("Publishing domain events across bus...\n")

    # Publish events
    await bus.publish(
        PlannerFinishedEvent(
            event_id="evt-101",
            session_id="sess-demo",
            goal_description="Refactor core architecture to Clean Architecture",
            step_count=4,
        )
    )

    await bus.publish(
        ToolFailedEvent(
            event_id="evt-102",
            session_id="sess-demo",
            tool_name="cloud_ocr_read",
            error_message="HTTP 504 Gateway Timeout after 30s",
        )
    )

    await bus.publish(
        ExecutionFinishedEvent(
            event_id="evt-103",
            session_id="sess-demo",
            success=True,
            executed_steps=4,
        )
    )

    print("\nEvent publishing complete.")


if __name__ == "__main__":
    asyncio.run(main())
