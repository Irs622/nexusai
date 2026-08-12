"""Unit tests for P2-1 Execution State & Persistence domain models, ports, and SQLite storage."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from typing import Any
import pytest

from nexusai.brain.domain.agent import AgentGoal, PlanGraph, PlanGraphNode, PlanningGoal, PlanStep
from nexusai.brain.domain.execution_state import (
    ExecutionRecord,
    ExecutionStatus,
    NodeExecutionRecord,
    NodeExecutionStatus,
    compute_plan_graph_hash,
)
from nexusai.brain.ports.tool_port import ToolExecutionResult
from nexusai.infrastructure.persistence.sqlite_execution_store import (
    SerializationError,
    SQLiteExecutionStateStore,
)


def create_test_graph() -> PlanGraph:
    nodes = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Step 1", tool_name="tool_1"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Step 2", tool_name="tool_2"), dependencies=(1,)),
    }
    return PlanGraph(nodes=nodes, edges=((1, 2),))


@pytest.mark.asyncio
async def test_A_execution_creation_and_loading() -> None:
    """Test A: Execution record and node records can be created and loaded from SQLite."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteExecutionStateStore(db_path=db_path)
        graph = create_test_graph()
        g_hash = compute_plan_graph_hash(graph)

        nodes = {
            1: NodeExecutionRecord(execution_id="exec-1", node_id=1, tool_name="tool_1"),
            2: NodeExecutionRecord(execution_id="exec-1", node_id=2, tool_name="tool_2"),
        }
        record = ExecutionRecord(
            execution_id="exec-1",
            plan_id="plan-1",
            graph_hash=g_hash,
            node_records=nodes,
        )

        await store.create_execution(record)
        loaded = await store.load_execution("exec-1")

        assert loaded is not None
        assert loaded.execution_id == "exec-1"
        assert loaded.plan_id == "plan-1"
        assert loaded.graph_hash == g_hash
        assert len(loaded.node_records) == 2
        assert loaded.node_records[1].status == NodeExecutionStatus.PENDING
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_B_node_initialization_state() -> None:
    """Test B: Initialized nodes receive durable PENDING state."""
    store = SQLiteExecutionStateStore(":memory:")
    graph = create_test_graph()
    record = ExecutionRecord(
        execution_id="exec-b",
        plan_id="plan-b",
        graph_hash=compute_plan_graph_hash(graph),
        node_records={
            1: NodeExecutionRecord(execution_id="exec-b", node_id=1),
        },
    )
    await store.create_execution(record)
    loaded = await store.load_execution("exec-b")
    assert loaded is not None
    assert loaded.node_records[1].status == NodeExecutionStatus.PENDING


@pytest.mark.asyncio
async def test_C_running_checkpoint_persistence() -> None:
    """Test C: RUNNING state transition is persisted in storage."""
    store = SQLiteExecutionStateStore(":memory:")
    graph = create_test_graph()
    record = ExecutionRecord(
        execution_id="exec-c",
        plan_id="plan-c",
        graph_hash=compute_plan_graph_hash(graph),
        node_records={1: NodeExecutionRecord(execution_id="exec-c", node_id=1)},
    )
    await store.create_execution(record)
    await store.mark_node_running("exec-c", 1)

    loaded = await store.load_execution("exec-c")
    assert loaded is not None
    assert loaded.node_records[1].status == NodeExecutionStatus.RUNNING
    assert loaded.node_records[1].started_at is not None


@pytest.mark.asyncio
async def test_D_successful_atomic_completion() -> None:
    """Test D: Result and COMPLETED state are committed atomically."""
    store = SQLiteExecutionStateStore(":memory:")
    graph = create_test_graph()
    record = ExecutionRecord(
        execution_id="exec-d",
        plan_id="plan-d",
        graph_hash=compute_plan_graph_hash(graph),
        node_records={1: NodeExecutionRecord(execution_id="exec-d", node_id=1)},
    )
    await store.create_execution(record)
    await store.mark_node_running("exec-d", 1)

    res = ToolExecutionResult(
        request_id="step-1",
        tool_name="tool_1",
        success=True,
        output={"status": "ok", "items": [1, 2, 3]},
    )
    await store.save_node_result_atomically("exec-d", 1, NodeExecutionStatus.COMPLETED, res)

    loaded = await store.load_execution("exec-d")
    assert loaded is not None
    assert loaded.node_records[1].status == NodeExecutionStatus.COMPLETED
    assert loaded.node_records[1].output == {"status": "ok", "items": [1, 2, 3]}


@pytest.mark.asyncio
async def test_E_failed_execution_checkpoint() -> None:
    """Test E: FAILED state and error message are persisted."""
    store = SQLiteExecutionStateStore(":memory:")
    graph = create_test_graph()
    record = ExecutionRecord(
        execution_id="exec-e",
        plan_id="plan-e",
        graph_hash=compute_plan_graph_hash(graph),
        node_records={1: NodeExecutionRecord(execution_id="exec-e", node_id=1)},
    )
    await store.create_execution(record)

    res = ToolExecutionResult(
        request_id="step-1",
        tool_name="tool_1",
        success=False,
        error_message="Network failure",
    )
    await store.save_node_result_atomically("exec-e", 1, NodeExecutionStatus.FAILED, res)

    loaded = await store.load_execution("exec-e")
    assert loaded is not None
    assert loaded.node_records[1].status == NodeExecutionStatus.FAILED
    assert loaded.node_records[1].error_message == "Network failure"


@pytest.mark.asyncio
async def test_F_cancellation_checkpoint() -> None:
    """Test F: CANCELLED state is persisted correctly."""
    store = SQLiteExecutionStateStore(":memory:")
    graph = create_test_graph()
    record = ExecutionRecord(
        execution_id="exec-f",
        plan_id="plan-f",
        graph_hash=compute_plan_graph_hash(graph),
        node_records={1: NodeExecutionRecord(execution_id="exec-f", node_id=1)},
    )
    await store.create_execution(record)
    await store.mark_node_cancelled("exec-f", 1)

    loaded = await store.load_execution("exec-f")
    assert loaded is not None
    assert loaded.node_records[1].status == NodeExecutionStatus.CANCELLED


@pytest.mark.asyncio
async def test_G_plan_mismatch_hash_protection() -> None:
    """Test G: Modified PlanGraph produces different structural hash for plan mismatch detection."""
    graph1 = create_test_graph()
    hash1 = compute_plan_graph_hash(graph1)

    # Modify graph structure
    nodes2 = {
        1: PlanGraphNode(step=PlanStep(step_id=1, title="Step 1", tool_name="tool_1"), dependencies=()),
        2: PlanGraphNode(step=PlanStep(step_id=2, title="Step 2 MODIFIED", tool_name="tool_2"), dependencies=(1,)),
    }
    graph2 = PlanGraph(nodes=nodes2, edges=((1, 2),))
    hash2 = compute_plan_graph_hash(graph2)

    assert hash1 != hash2, "Structural plan graph hash must change when graph nodes are modified"


@pytest.mark.asyncio
async def test_H_concurrent_checkpoints() -> None:
    """Test H: Concurrent node checkpoints do not cause database locking or corruption."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = SQLiteExecutionStateStore(db_path=db_path)
        nodes = {i: NodeExecutionRecord(execution_id="exec-h", node_id=i) for i in range(1, 10)}
        record = ExecutionRecord(
            execution_id="exec-h",
            plan_id="plan-h",
            graph_hash="hash-h",
            node_records=nodes,
        )
        await store.create_execution(record)

        async def checkpoint_node(node_id: int) -> None:
            await store.mark_node_running("exec-h", node_id)
            res = ToolExecutionResult(request_id=f"step-{node_id}", tool_name=f"tool_{node_id}", success=True, output=f"res_{node_id}")
            await store.save_node_result_atomically("exec-h", node_id, NodeExecutionStatus.COMPLETED, res)

        tasks = [checkpoint_node(i) for i in range(1, 10)]
        await asyncio.gather(*tasks)

        loaded = await store.load_execution("exec-h")
        assert loaded is not None
        assert all(n.status == NodeExecutionStatus.COMPLETED for n.values in [loaded.node_records] for n in n.values())
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_I_serialization_safety_and_payload_limits() -> None:
    """Test I: JSON-compatible outputs succeed; non-serializable objects or oversized payloads fail explicitly."""
    store = SQLiteExecutionStateStore(":memory:", max_payload_bytes=100)
    graph = create_test_graph()
    record = ExecutionRecord(
        execution_id="exec-i",
        plan_id="plan-i",
        graph_hash=compute_plan_graph_hash(graph),
        node_records={1: NodeExecutionRecord(execution_id="exec-i", node_id=1)},
    )
    await store.create_execution(record)

    # 1. Non-serializable object
    class CustomUnserializableObj:
        pass

    unserializable_res = ToolExecutionResult(
        request_id="step-1",
        tool_name="tool_1",
        success=True,
        output=CustomUnserializableObj(),
    )
    with pytest.raises(SerializationError, match="not JSON-serializable"):
        await store.save_node_result_atomically("exec-i", 1, NodeExecutionStatus.COMPLETED, unserializable_res)

    # 2. Oversized payload exceeding 100 bytes limit
    oversized_res = ToolExecutionResult(
        request_id="step-1",
        tool_name="tool_1",
        success=True,
        output={"large_data": "x" * 200},
    )
    with pytest.raises(SerializationError, match="exceeds max limit"):
        await store.save_node_result_atomically("exec-i", 1, NodeExecutionStatus.COMPLETED, oversized_res)


@pytest.mark.asyncio
async def test_J_idempotency_limitation_documentation() -> None:
    """Test J: Document that persistence provides durable knowledge of completed work, but not side-effect idempotency."""
    store = SQLiteExecutionStateStore(":memory:")
    graph = create_test_graph()
    record = ExecutionRecord(
        execution_id="exec-j",
        plan_id="plan-j",
        graph_hash=compute_plan_graph_hash(graph),
        node_records={1: NodeExecutionRecord(execution_id="exec-j", node_id=1)},
    )
    await store.create_execution(record)
    await store.mark_node_running("exec-j", 1)

    # Process crashes here: External tool side effect occurred, but DB checkpoint was never called!
    loaded_after_crash = await store.load_execution("exec-j")
    assert loaded_after_crash is not None
    assert loaded_after_crash.node_records[1].status == NodeExecutionStatus.RUNNING, (
        "Uncommitted RUNNING node must not be assumed completed after process crash"
    )


if __name__ == "__main__":
    asyncio.run(test_A_execution_creation_and_loading())
    asyncio.run(test_B_node_initialization_state())
    asyncio.run(test_C_running_checkpoint_persistence())
    asyncio.run(test_D_successful_atomic_completion())
    asyncio.run(test_E_failed_execution_checkpoint())
    asyncio.run(test_F_cancellation_checkpoint())
    asyncio.run(test_G_plan_mismatch_hash_protection())
    asyncio.run(test_H_concurrent_checkpoints())
    asyncio.run(test_I_serialization_safety_and_payload_limits())
    asyncio.run(test_J_idempotency_limitation_documentation())
    print("ALL P2-1 PERSISTENCE UNIT TESTS PASSED SUCCESSFULLY!")
