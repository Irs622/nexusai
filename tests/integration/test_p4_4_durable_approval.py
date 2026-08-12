"""Integration test suite for P4-4 Durable Approval restart recovery simulation."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.governance import ResourceBudget, ToolCapability
from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalStatus,
    HumanApprovalDecision,
    HumanApprovalRequest,
    RiskLevel,
)
from nexusai.brain.domain.tool_registry import ToolMetadata, ToolStatus, ToolTrustLevel
from nexusai.brain.runtime.governance_engine import GovernanceEngine
from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine
from nexusai.brain.runtime.tool_registry import ToolRegistry
from nexusai.infrastructure.persistence.sqlite_approval_store import SQLiteApprovalStore
from tests.fixtures.p4_1_tools import ControlledTestToolPort


@pytest.mark.asyncio
async def test_durable_approval_restart_recovery_simulation() -> None:
    """Simulation: Process A creates request -> Process A terminates -> Process B reads DB & Approves -> Process C verifies, re-validates, & executes."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        binding = ActionBinding(
            session_id="sess-restart-1",
            execution_id="exec-restart-1",
            plan_fingerprint="fp-restart-1",
            node_id="n1",
            tool_id="process_exec_tool",
            tool_version="1.0.0",
            requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        )

        # Step 1: Process A creates request in SQLite DB
        store_a = SQLiteApprovalStore(db_path=db_path)
        engine_a = HumanApprovalEngine(store=store_a)
        req_a = HumanApprovalRequest("app-restart-1", binding, RiskLevel.HIGH, "Run process")
        await engine_a.request_approval(req_a)

        # Process A terminates (instance discarded)
        del engine_a, store_a

        # Step 2: Process B initializes, loads persisted request, and submits APPROVED decision
        store_b = SQLiteApprovalStore(db_path=db_path)
        engine_b = HumanApprovalEngine(store=store_b)

        req_b = await engine_b.get_request("app-restart-1")
        assert req_b is not None
        assert req_b.status == ApprovalStatus.PENDING

        dec_b = HumanApprovalDecision("app-restart-1", ApprovalStatus.APPROVED, "operator_b@co.com", "Approved post-restart")
        grant_b = await engine_b.submit_decision(dec_b)

        del engine_b, store_b

        # Step 3: Process C initializes, verifies grant, re-validates ToolRegistry & Governance, and dispatches tool
        store_c = SQLiteApprovalStore(db_path=db_path)
        engine_c = HumanApprovalEngine(store=store_c)
        registry_c = ToolRegistry()
        gov_c = GovernanceEngine(global_budget=ResourceBudget(max_tool_invocations=10))

        tool_meta = ToolMetadata("process_exec_tool", "ProcessTool", "1.0.0", "ProcessTool", frozenset({ToolCapability.PROCESS_EXEC}), status=ToolStatus.ENABLED)
        await registry_c.register(tool_meta)

        # 1. Verify single-use grant
        assert await engine_c.verify_and_consume_grant(grant_b.grant_id, binding) is True

        # 2. Re-validate ToolRegistry
        await registry_c.validate_tool("process_exec_tool")

        # 3. Re-validate Governance Admission
        gov_res = await gov_c.authorize("exec-restart-1", binding.requested_capabilities)
        assert gov_res.allowed is True

        # 4. Dispatch tool execution
        tool_port = ControlledTestToolPort()
        res = await tool_port.execute(pytest.importorskip("nexusai.brain.ports.tool_port").ToolExecutionRequest("exec-restart-1", "process_exec_tool", ()))
        assert res.success is True
        assert tool_port.call_count == 1

        await gov_c.release(gov_res.reservation_id)
        assert gov_c.get_active_reservation_count() == 0

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_durable_approval_restart_recovery_simulation())
    print("ALL DURABLE APPROVAL INTEGRATION RESTART RECOVERY TESTS PASSED SUCCESSFULLY!")
