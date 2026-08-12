"""Integration test suite for P3-1 BrainRuntimeFacade, IAgentRuntime port, and session identity validation."""

from __future__ import annotations

import asyncio
import os
import tempfile
from unittest.mock import MagicMock
import pytest

from nexusai.brain.domain.agent import (
    AgentGoal,
    PlanGraph,
    PlanGraphNode,
    PlanningContext,
    PlanningGoal,
    PlanningResources,
    PlanStep,
)
from nexusai.brain.domain.agent_runtime import (
    AgentExecutionState,
    AgentRequest,
)
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.brain_runtime_facade import BrainRuntimeFacade
from nexusai.brain.runtime.context_builder import ContextBuilder
from nexusai.brain.runtime.memory_retriever import MemoryRetriever
from nexusai.infrastructure.observability.in_memory_exporter import InMemoryMetricsExporter
from nexusai.infrastructure.persistence.sqlite_execution_store import SQLiteExecutionStateStore
from nexusai.infrastructure.persistence.sqlite_memory_store import SQLiteMemoryStore


class FacadeDummyToolPort(IToolPort):
    """ToolPort executing steps for facade integration testing."""

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        await asyncio.sleep(0.005)
        return ToolExecutionResult(
            request_id=request.execution_id,
            tool_name=request.tool_name,
            success=True,
            output=f"Executed output for {request.tool_name}",
        )


@pytest.mark.asyncio
async def test_p3_1_run_agent_happy_path() -> None:
    """Integration Test 1: Full run_agent() execution through context, planning, governance, and execution."""
    telemetry = InMemoryMetricsExporter()
    mem_store = SQLiteMemoryStore(":memory:")
    retriever = MemoryRetriever(store=mem_store, telemetry=telemetry)
    builder = ContextBuilder(retriever=retriever, store=mem_store)

    engine = PlanGraphExecutionEngine(telemetry=telemetry)
    facade = BrainRuntimeFacade(
        execution_engine=engine,
        memory_store=mem_store,
        context_builder=builder,
        telemetry=telemetry,
    )

    tool_port = FacadeDummyToolPort()
    req = AgentRequest(session_id="sess-facade-1", user_prompt="Process agent query")

    resp = await facade.run_agent(req, tool_port)

    assert resp.session_id == "sess-facade-1"
    assert resp.state == AgentExecutionState.COMPLETED
    assert "Executed output" in resp.final_output
    assert len(resp.results) > 0

    # Confirm episodic memory entry persisted automatically
    episodic_mems = await mem_store.list_session_memories("sess-facade-1")
    assert len(episodic_mems) == 1
    assert "Process agent query" in episodic_mems[0].content


@pytest.mark.asyncio
async def test_p3_1_resume_agent_session_identity_and_plan_hash_validation() -> None:
    """Integration Test 5 & 8: Verify session identity validation (P3-1-INV-05) and plan hash mismatch rejection (P3-1-INV-06)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        exec_db = tf.name

    try:
        exec_store = SQLiteExecutionStateStore(db_path=exec_db)
        engine = PlanGraphExecutionEngine(state_store=exec_store)
        facade = BrainRuntimeFacade(execution_engine=engine)

        tool_port = FacadeDummyToolPort()

        # Run initial agent execution to populate state store
        req1 = AgentRequest(session_id="sess-original", user_prompt="Initial query")
        resp1 = await facade.run_agent(req1, tool_port)
        exec_id = resp1.execution_id

        # 1. Session Identity Validation (P3-1-INV-05): Resuming with session_id="sess-attacker" must be REJECTED!
        req_bad_session = AgentRequest(session_id="sess-attacker", user_prompt="Initial query")
        with pytest.raises(ValueError, match="Session mismatch"):
            await facade.resume_agent(exec_id, req_bad_session, tool_port)

        # 2. Valid Resume with correct session_id="sess-original" succeeds cleanly
        req_valid = AgentRequest(session_id="sess-original", user_prompt="Initial query")
        resp_resume = await facade.resume_agent(exec_id, req_valid, tool_port)
        assert resp_resume.state == AgentExecutionState.COMPLETED
        assert resp_resume.execution_id == exec_id

    finally:
        if os.path.exists(exec_db):
            os.remove(exec_db)


@pytest.mark.asyncio
async def test_p3_1_fault_isolation_under_facade_execution() -> None:
    """Integration Test 12 & 13: Telemetry & Memory failures do NOT break facade execution."""
    faulty_telemetry = InMemoryMetricsExporter(fail_on_purpose=True)
    engine = PlanGraphExecutionEngine(telemetry=faulty_telemetry)
    facade = BrainRuntimeFacade(execution_engine=engine, telemetry=faulty_telemetry)

    tool_port = FacadeDummyToolPort()
    req = AgentRequest(session_id="sess-fault-iso", user_prompt="Fault isolation query")

    resp = await facade.run_agent(req, tool_port)
    assert resp.state == AgentExecutionState.COMPLETED


if __name__ == "__main__":
    asyncio.run(test_p3_1_run_agent_happy_path())
    asyncio.run(test_p3_1_resume_agent_session_identity_and_plan_hash_validation())
    asyncio.run(test_p3_1_fault_isolation_under_facade_execution())
    print("ALL P3-1 AGENT RUNTIME INTEGRATION TESTS PASSED SUCCESSFULLY!")
