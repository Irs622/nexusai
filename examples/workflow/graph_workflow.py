"""Example StateGraph workflow execution for NexusAI."""

import asyncio

from nexusai.brain.workflow.graph import build_brain_workflow


async def main() -> None:
    # Build workflow graph
    _workflow = build_brain_workflow()
    print("Workflow Graph compiled successfully!")


if __name__ == "__main__":
    asyncio.run(main())
