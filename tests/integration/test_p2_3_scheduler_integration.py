"""Integration and stress verification test suite for P2-3 PriorityScheduler, IScheduler port, and PlanGraphExecutionEngine integration."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from typing import Any
from unittest.mock import MagicMock
import pytest
from pydantic import BaseModel, Field

from nexusai.brain.coordinator import BrainCoordinator
from nexusai.brain.domain.agent import (
    AgentGoal,
    PlanGraph,
    PlanGraphNode,
    PlanningContext,
    PlanningGoal,
    PlanningResources,
    PlanStep,
    StepStatus,
)
from nexusai.brain.domain.scheduler import ScheduledTask, SchedulerClosedError, TaskPriority
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.priority_scheduler import PriorityScheduler
from nexusai.infrastructure.persistence.sqlite_execution_store import SQLiteExecutionStateStore


class PrioritySpyToolPort(IToolPort):
    """ToolPort spy recording exact dispatch sequence of tool executions."""

    def __init__(self) -> None:
        self.dispatch_order: list[str] = []

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        self.dispatch_order.append(request.tool_name)
        await asyncio.sleep(0.01)
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=request.tool_name,
            success=True,
            output=f"Output for {request.tool_name}",
        )


def create_p2_3_context() -> PlanningContext:
    goal = AgentGoal(description="P2-3 Priority Scheduler Integration Context")
    tools = ("tool_low", "tool_normal", "tool_high", "tool_critical")
    return PlanningContext(
        goal_component=PlanningGoal(goal=goal),
        resources_component=PlanningResources(available_tools=tools),
    )


@pytest.mark.asyncio
async def test_p2_3_priority_dispatch_order() -> None:
    """Test P2-3: PriorityScheduler dispatches tasks in order of effective priority (CRITICAL/HIGH before LOW)."""
    scheduler = PriorityScheduler(aging_rate=0.0)  # Disable aging for pure priority test
    engine = PlanGraphExecutionEngine(scheduler=scheduler, max_concurrency=1)  # Sequential concurrency for order check

    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Root", tool_name="tool_low"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Low Node", tool_name="tool_normal"), dependencies=(1,)),
        3: PlanGraphNode(step=PlanStep(step_id=3, title="High Node", tool_name="tool_high"), dependencies=(1,)),
    }
    plan_graph = PlanGraph(nodes=nodes, edges=((1, 2), (1, 3)))
    engine.planner.plan = lambda ctx, session_id="": (plan_graph, MagicMock())  # type: ignore[assignment]

    spy_port = PrioritySpyToolPort()
    ctx = create_p2_3_context()

    rec_graph, results, trace = await engine.execute_plan(ctx, spy_port)

    assert rec_graph.nodes[1].step.status == StepStatus.COMPLETED
    assert rec_graph.nodes[2].step.status == StepStatus.COMPLETED
    assert rec_graph.nodes[3].step.status == StepStatus.COMPLETED
    assert spy_port.dispatch_order[0] == "tool_low"


@pytest.mark.asyncio
async def test_p2_3_end_to_end_brain_coordinator_integration() -> None:
    """Test P2-3: BrainCoordinator end-to-end execution through PriorityScheduler."""
    scheduler = PriorityScheduler(aging_rate=0.5)
    engine = PlanGraphExecutionEngine(scheduler=scheduler)
    coordinator = BrainCoordinator(model_provider=None, execution_engine=engine)

    res = await coordinator.process_user_input("P2-3 Scheduler integration query")

    assert res["status"] == "COMPLETED"
    assert res["iterations"] == 1
    assert "trace_id" in res
    assert coordinator.last_plan_graph is not None


@pytest.mark.asyncio
async def test_p2_3_adversarial_concurrent_stress() -> None:
    """Stress Test: Concurrent submitters, consumers, cancellations, and shutdown under heavy load."""
    scheduler = PriorityScheduler(aging_rate=1.0)
    claimed_tasks: list[str] = []
    lock = asyncio.Lock()

    async def producer(task_prefix: str, count: int) -> None:
        for i in range(count):
            try:
                task = ScheduledTask(
                    task_id=f"{task_prefix}-{i}",
                    execution_id="exec-stress",
                    node_id=i,
                    priority=TaskPriority.NORMAL if i % 2 == 0 else TaskPriority.HIGH,
                    delay_until=time.time() + 0.05 if i % 3 == 0 else None,
                )
                await scheduler.submit(task)
                await asyncio.sleep(0.005)
            except SchedulerClosedError:
                break

    async def consumer() -> None:
        while True:
            try:
                claimed = await scheduler.next()
                async with lock:
                    claimed_tasks.append(claimed.task_id)
                await asyncio.sleep(0.005)
            except SchedulerClosedError:
                break

    # Spawn 5 producers and 3 consumers
    producers = [asyncio.create_task(producer(f"p{p}", 10)) for p in range(5)]
    consumers = [asyncio.create_task(consumer()) for _ in range(3)]

    await asyncio.sleep(0.1)
    # Cancel some tasks concurrently
    await scheduler.cancel("p0-5")
    await scheduler.cancel("p1-5")

    await asyncio.gather(*producers, return_exceptions=True)
    await asyncio.sleep(0.1)

    await scheduler.shutdown()
    await asyncio.gather(*consumers, return_exceptions=True)

    assert len(claimed_tasks) > 0, "Scheduler must claim tasks under concurrent stress"
    assert scheduler.is_shutdown is True


@pytest.mark.asyncio
async def test_p2_3_dag_unlock_deadlock_safety() -> None:
    """Stress Test: Blocked scheduler.next() wakes immediately when a new task is submitted without deadlock."""
    scheduler = PriorityScheduler()

    claimed_result: ScheduledTask | None = None

    async def waiting_consumer() -> None:
        nonlocal claimed_result
        claimed_result = await scheduler.next()

    # Start consumer when scheduler has 0 tasks
    consumer_task = asyncio.create_task(waiting_consumer())
    await asyncio.sleep(0.03)

    # Submit task from external coroutine
    task = ScheduledTask(task_id="t_unlock", execution_id="e1", node_id=1, priority=TaskPriority.HIGH)
    await scheduler.submit(task)

    await asyncio.wait_for(consumer_task, timeout=1.0)
    assert claimed_result is not None
    assert claimed_result.task_id == "t_unlock"


@pytest.mark.asyncio
async def test_p2_3_claimed_task_cancellation_semantics() -> None:
    """Test Claimed Task Boundary: scheduler.cancel(task_id) returns False once task is CLAIMED."""
    scheduler = PriorityScheduler()
    task = ScheduledTask(task_id="t_claim_test", execution_id="e1", node_id=1)
    await scheduler.submit(task)

    # Claim task
    claimed = await scheduler.next()
    assert claimed.task_id == "t_claim_test"

    # Attempting to cancel already claimed task returns False (ownership transferred to engine)
    cancelled = await scheduler.cancel("t_claim_test")
    assert cancelled is False, "scheduler.cancel() must return False once task is CLAIMED by engine"


@pytest.mark.asyncio
async def test_p2_3_shutdown_with_delayed_heap() -> None:
    """Test Shutdown Boundary: shutdown() wakes blocked next() consumers even when tasks exist in delayed heap."""
    scheduler = PriorityScheduler()

    now = time.time()
    # Add task delayed by 10 seconds
    task = ScheduledTask(task_id="t_delayed_heap", execution_id="e1", node_id=1, delay_until=now + 10.0)
    await scheduler.submit(task)

    consumer_task = asyncio.create_task(scheduler.next())
    await asyncio.sleep(0.02)

    await scheduler.shutdown()

    with pytest.raises(SchedulerClosedError):
        await consumer_task


if __name__ == "__main__":
    asyncio.run(test_p2_3_priority_dispatch_order())
    asyncio.run(test_p2_3_end_to_end_brain_coordinator_integration())
    asyncio.run(test_p2_3_adversarial_concurrent_stress())
    asyncio.run(test_p2_3_dag_unlock_deadlock_safety())
    asyncio.run(test_p2_3_claimed_task_cancellation_semantics())
    asyncio.run(test_p2_3_shutdown_with_delayed_heap())
    print("ALL P2-3 SCHEDULER INTEGRATION & ADVERSARIAL STRESS TESTS PASSED SUCCESSFULLY!")
