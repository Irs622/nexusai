"""Basic Agent Example — NexusAI Agent Runtime."""

from __future__ import annotations

import asyncio

from nexusai.brain.domain.agent import AgentGoal, PlanningContext, PlanningGoal, PlanningResources
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult


class BasicToolPort(IToolPort):
    """Simple mock tool port implementation."""

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        print(f"  [ToolPort] Executing tool: {request.tool_name} with args: {request.arguments}")
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=request.tool_name,
            success=True,
            result_data=f"Successfully executed {request.tool_name}",
        )


async def main() -> None:
    print("=== NexusAI Basic Agent Demo ===")
    goal = AgentGoal(description="Locate, read, and summarize system configuration file")
    ctx = PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=("summarize_file",)),
    )

    engine = PlanGraphExecutionEngine()
    tool_port = BasicToolPort()

    print(f"Goal: {goal.description}")
    print("Executing plan via PlanGraphExecutionEngine...")

    graph, results, trace = await engine.execute_plan(
        ctx, tool_port=tool_port, session_id="demo-basic-session"
    )

    print("\nExecution Complete!")
    print(f"Total DAG Plan Nodes: {len(graph.nodes)}")
    print(f"Total Executed Results: {len(results)}")
    for res in results:
        print(f"  - [{res.tool_name}] Success={res.success} Data={res.result_data}")


if __name__ == "__main__":
    asyncio.run(main())
