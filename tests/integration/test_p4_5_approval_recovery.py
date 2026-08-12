"""Human approval recovery integration test suite for P4-5 Crash Recovery."""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from nexusai.brain.domain.execution_recovery import JournalEntry, JournalLifecyclePhase
from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.human_approval import ActionBinding, ApprovalStatus, HumanApprovalDecision, HumanApprovalRequest, RiskLevel
from nexusai.brain.runtime.crash_recovery_manager import CrashRecoveryManager
from nexusai.brain.runtime.human_approval_engine import HumanApprovalEngine
from nexusai.infrastructure.persistence.sqlite_approval_store import SQLiteApprovalStore
from nexusai.infrastructure.persistence.sqlite_execution_journal import SQLiteExecutionJournal


@pytest.mark.asyncio
async def test_approval_grant_recovery_preserves_consumed_status() -> None:
    """Verify CrashRecoveryManager does not resurrect consumed approval grants."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        journal = SQLiteExecutionJournal(db_path=db_path)
        approval_store = SQLiteApprovalStore(db_path=db_path)
        approval_engine = HumanApprovalEngine(store=approval_store)
        mgr = CrashRecoveryManager(journal=journal, approval_engine=approval_engine)

        binding = ActionBinding(
            session_id="sess-app-rec",
            execution_id="exec-app-rec",
            plan_fingerprint="fp-app-rec",
            node_id="n1",
            tool_id="process_tool",
            tool_version="1.0.0",
            requested_capabilities=frozenset({ToolCapability.PROCESS_EXEC}),
        )

        req = HumanApprovalRequest("app-rec-1", binding, RiskLevel.HIGH, "Run process")
        await approval_engine.request_approval(req)

        dec = HumanApprovalDecision("app-rec-1", ApprovalStatus.APPROVED, "op@co.com", "Approved")
        grant = await approval_engine.submit_decision(dec)

        # Consume grant
        await approval_engine.verify_and_consume_grant(grant.grant_id, binding)

        # Journal records crash after grant consumption
        entry = JournalEntry(
            entry_id="j-app-rec-1",
            session_id="sess-app-rec",
            execution_id="exec-app-rec",
            plan_fingerprint="fp-app-rec",
            node_id="n1",
            tool_id="process_tool",
            action_digest=binding.action_digest,
            phase=JournalLifecyclePhase.EXECUTING_TOOL,
            approval_grant_id=grant.grant_id,
        )
        await journal.append_entry(entry)

        # Attempt recovery -> Must fail closed because grant is CONSUMED and tool execution is non-idempotent!
        await mgr.recover_execution("exec-app-rec")

        req_after = await approval_engine.get_request("app-rec-1")
        assert req_after is not None
        assert req_after.status == ApprovalStatus.CONSUMED, "Consumed approval grant MUST NOT be resurrected into APPROVED!"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    asyncio.run(test_approval_grant_recovery_preserves_consumed_status())
    print("ALL P4-5 APPROVAL RECOVERY TESTS PASSED SUCCESSFULLY!")
